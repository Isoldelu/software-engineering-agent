"""Reviewed, idempotent bridge from offline evolution to policy rollout."""

from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from typing import Any

from app.evolution.candidate import EvolutionConfigValidator
from app.evolution.models import EvolutionCandidate, EvolutionPolicyBridge
from app.evolution.repository import (
    DEFAULT_EVOLUTION_REPOSITORY,
    EvolutionRepository,
)
from app.policy.engine import DEFAULT_POLICY_REPOSITORY, PolicyConfigValidator
from app.policy.repository import PolicyRepository
from app.storage.database import ConcurrentUpdateError


class EvolutionPolicyTranslator:
    def translate(self, candidate: EvolutionCandidate) -> dict[str, Any]:
        if candidate.asset_type == "router_rule":
            return {"rules": deepcopy(candidate.config["rules"])}
        if candidate.asset_type == "query_alias":
            return {"aliases": deepcopy(candidate.config["aliases"])}
        if candidate.asset_type == "retriever_weights":
            return {
                "retriever": {
                    "mode": candidate.config["mode"],
                    "rrf_weight": candidate.config["rrf_weight"],
                    "reranker_weight": candidate.config["reranker_weight"],
                }
            }
        raise ValueError(f"Unsupported evolution asset: {candidate.asset_type}")

    def merge(
        self,
        stable_config: dict[str, Any],
        patch: dict[str, Any],
    ) -> dict[str, Any]:
        merged = deepcopy(stable_config)
        merged.setdefault("rules", [])
        if "rules" in patch:
            incoming = patch["rules"]
            incoming_ids = {item["hook_id"] for item in incoming}
            merged["rules"] = [
                item for item in merged.get("rules", [])
                if item.get("hook_id") not in incoming_ids
            ] + deepcopy(incoming)
        if "aliases" in patch:
            merged.setdefault("aliases", {})
            merged["aliases"].update(deepcopy(patch["aliases"]))
        if "retriever" in patch:
            merged["retriever"] = deepcopy(patch["retriever"])
        return merged


class EvolutionPolicyBridgeService:
    def __init__(
        self,
        *,
        evolution: EvolutionRepository,
        policies: PolicyRepository,
    ) -> None:
        self.evolution = evolution
        self.policies = policies
        self.translator = EvolutionPolicyTranslator()

    def release(
        self,
        candidate_id: str,
        *,
        rollout_percentage: float,
        released_by: str,
    ) -> dict[str, Any]:
        candidate = self._candidate(candidate_id)
        self._validate_candidate(candidate, released_by=released_by)
        patch = self.translator.translate(candidate)
        config = self.translator.merge(self.policies.stable().config, patch)
        policy_issues = PolicyConfigValidator().validate(config)
        if policy_issues:
            raise ValueError(f"Translated policy config is invalid: {policy_issues}")

        candidate_digest = _digest(_candidate_material(candidate))
        config_digest = _digest(config)
        bridge_id = f"bridge_{candidate_digest[:20]}"
        source_id = f"evolution:{candidate.candidate_id}:{candidate_digest[:12]}"
        existing_bridge = self.evolution.get_bridge(bridge_id)
        if existing_bridge:
            if existing_bridge.rollout_percentage != float(rollout_percentage):
                raise ValueError(
                    "Evolution candidate was already released with a different "
                    "rollout percentage."
                )
            policy = self.policies.get(existing_bridge.policy_id)
            if not policy:
                raise RuntimeError("Bridge references a missing policy version.")
            self._sync_candidate(candidate, existing_bridge, policy.status)
            return self._response(existing_bridge, policy.to_dict(), created=False)
        if candidate.active:
            raise ValueError("Evolution candidate already has an active policy.")

        policy, created = self.policies.create_rollout_once(
            config=config,
            source_candidate_id=source_id,
            rollout_percentage=rollout_percentage,
            metadata={
                "bridge_schema_version": "evolution-policy-bridge-v1",
                "bridge_id": bridge_id,
                "evolution_candidate_id": candidate.candidate_id,
                "evolution_asset_type": candidate.asset_type,
                "candidate_digest": candidate_digest,
                "config_digest": config_digest,
                "source_cluster_id": candidate.source_cluster_id,
                "source_failure_ids": list(candidate.source_failure_ids),
                "shadow_summary": {
                    "passed": candidate.shadow_evaluation["passed"],
                    "fixed_bad_case_count": candidate.shadow_evaluation.get(
                        "fixed_bad_case_count", 0
                    ),
                    "regressed_case_count": candidate.shadow_evaluation.get(
                        "regressed_case_count", 0
                    ),
                },
                "reviewer": candidate.review["reviewer"],
                "released_by": released_by.strip(),
            },
        )
        bridge = EvolutionPolicyBridge(
            bridge_id=bridge_id,
            schema_version="evolution-policy-bridge-v1",
            candidate_id=candidate.candidate_id,
            candidate_digest=candidate_digest,
            policy_source_id=source_id,
            policy_id=policy.policy_id,
            policy_version=policy.version,
            rollout_percentage=float(rollout_percentage),
            released_by=released_by.strip(),
            reviewer=candidate.review["reviewer"],
            config_digest=config_digest,
            created_at=policy.created_at,
        )
        bridge, bridge_created = self.evolution.save_bridge_once(bridge)
        self._sync_candidate(candidate, bridge, policy.status)
        return self._response(
            bridge,
            policy.to_dict(),
            created=created and bridge_created,
        )

    def list(self) -> list[dict[str, Any]]:
        return [item.to_dict() for item in self.evolution.bridges()]

    def _validate_candidate(
        self,
        candidate: EvolutionCandidate,
        *,
        released_by: str,
    ) -> None:
        if not released_by.strip():
            raise ValueError("released_by is required")
        if candidate.status != "approved":
            raise ValueError("Only an approved evolution candidate can be released.")
        if candidate.review.get("decision") != "approve":
            raise ValueError("Evolution candidate has no approving review decision.")
        if not candidate.review.get("reviewer", "").strip():
            raise ValueError("Evolution candidate reviewer is required.")
        if candidate.shadow_evaluation.get("passed") is not True:
            raise ValueError("Evolution candidate has not passed shadow evaluation.")
        issues = EvolutionConfigValidator().validate(candidate)
        if issues:
            raise ValueError(f"Evolution candidate is invalid: {issues}")

    def _candidate(self, candidate_id: str) -> EvolutionCandidate:
        candidate = self.evolution.get_candidate(candidate_id)
        if not candidate:
            raise KeyError(f"Evolution candidate not found: {candidate_id}")
        return candidate

    def _sync_candidate(
        self,
        candidate: EvolutionCandidate,
        bridge: EvolutionPolicyBridge,
        policy_status: str,
    ) -> None:
        candidate.active = policy_status in {"rollout", "active"}
        candidate.review["activation_status"] = policy_status
        candidate.review["bridge"] = {
            "bridge_id": bridge.bridge_id,
            "policy_id": bridge.policy_id,
            "policy_version": bridge.policy_version,
            "config_digest": bridge.config_digest,
        }
        try:
            self.evolution.save_candidate(candidate)
        except ConcurrentUpdateError:
            latest = self._candidate(candidate.candidate_id)
            if latest.review.get("bridge", {}).get("policy_id") != bridge.policy_id:
                raise

    def _response(
        self,
        bridge: EvolutionPolicyBridge,
        policy: dict[str, Any],
        *,
        created: bool,
    ) -> dict[str, Any]:
        return {
            "bridge": bridge.to_dict(),
            "policy": policy,
            "created": created,
            "idempotent_replay": not created,
            "assignment_state": self.policies.state(),
        }


def _candidate_material(candidate: EvolutionCandidate) -> dict[str, Any]:
    return {
        "candidate_id": candidate.candidate_id,
        "asset_type": candidate.asset_type,
        "config": candidate.config,
        "shadow_evaluation": candidate.shadow_evaluation,
        "review": {
            "decision": candidate.review.get("decision"),
            "reviewer": candidate.review.get("reviewer"),
            "reviewed_at": candidate.review.get("reviewed_at"),
        },
    }


def _digest(value: dict[str, Any]) -> str:
    serialized = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


DEFAULT_EVOLUTION_POLICY_BRIDGE = EvolutionPolicyBridgeService(
    evolution=DEFAULT_EVOLUTION_REPOSITORY,
    policies=DEFAULT_POLICY_REPOSITORY,
)
