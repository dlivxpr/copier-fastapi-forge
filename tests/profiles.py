from __future__ import annotations

from itertools import combinations, product
from typing import Any

INACTIVE = "<inactive>"

FACTOR_VALUES: dict[str, tuple[object, ...]] = {
    "database": ("none", "postgresql"),
    "orm_type": (INACTIVE, "sqlalchemy", "sqlmodel"),
    "include_example_crud": (INACTIVE, False, True),
    "background_tasks": ("none", "taskiq"),
    "enable_redis": (False, True),
    "enable_caching": (False, True),
    "enable_rate_limiting": (False, True),
    "rate_limit_storage": (INACTIVE, "memory", "redis"),
    "ai_framework": ("none", "pydantic_ai"),
    "enable_logfire": (INACTIVE, False, True),
    "enable_cors": (False, True),
    "enable_docker": (False, True),
    "reverse_proxy": (INACTIVE, "none", "nginx_external"),
    "ci_type": ("none", "github"),
}

PROFILE_STATES: dict[str, dict[str, object]] = {
    "minimal": {
        "database": "none",
        "orm_type": INACTIVE,
        "include_example_crud": INACTIVE,
        "background_tasks": "none",
        "enable_redis": False,
        "enable_caching": False,
        "enable_rate_limiting": False,
        "rate_limit_storage": INACTIVE,
        "ai_framework": "none",
        "enable_logfire": INACTIVE,
        "enable_cors": False,
        "enable_docker": False,
        "reverse_proxy": INACTIVE,
        "ci_type": "none",
    },
    "default": {
        "database": "postgresql",
        "orm_type": "sqlalchemy",
        "include_example_crud": False,
        "background_tasks": "none",
        "enable_redis": False,
        "enable_caching": False,
        "enable_rate_limiting": False,
        "rate_limit_storage": INACTIVE,
        "ai_framework": "pydantic_ai",
        "enable_logfire": True,
        "enable_cors": True,
        "enable_docker": True,
        "reverse_proxy": "nginx_external",
        "ci_type": "github",
    },
    "all_retained_sqlalchemy": {
        "database": "postgresql",
        "orm_type": "sqlalchemy",
        "include_example_crud": True,
        "background_tasks": "taskiq",
        "enable_redis": True,
        "enable_caching": True,
        "enable_rate_limiting": True,
        "rate_limit_storage": "redis",
        "ai_framework": "pydantic_ai",
        "enable_logfire": True,
        "enable_cors": True,
        "enable_docker": True,
        "reverse_proxy": "nginx_external",
        "ci_type": "github",
    },
    "all_retained_sqlmodel": {
        "database": "postgresql",
        "orm_type": "sqlmodel",
        "include_example_crud": True,
        "background_tasks": "taskiq",
        "enable_redis": True,
        "enable_caching": True,
        "enable_rate_limiting": True,
        "rate_limit_storage": "redis",
        "ai_framework": "pydantic_ai",
        "enable_logfire": True,
        "enable_cors": True,
        "enable_docker": True,
        "reverse_proxy": "nginx_external",
        "ci_type": "github",
    },
    "agent_logfire": {
        "database": "none",
        "orm_type": INACTIVE,
        "include_example_crud": INACTIVE,
        "background_tasks": "none",
        "enable_redis": False,
        "enable_caching": False,
        "enable_rate_limiting": False,
        "rate_limit_storage": INACTIVE,
        "ai_framework": "pydantic_ai",
        "enable_logfire": True,
        "enable_cors": False,
        "enable_docker": False,
        "reverse_proxy": INACTIVE,
        "ci_type": "none",
    },
    "redis_consumers_taskiq": {
        "database": "none",
        "orm_type": INACTIVE,
        "include_example_crud": INACTIVE,
        "background_tasks": "taskiq",
        "enable_redis": True,
        "enable_caching": True,
        "enable_rate_limiting": True,
        "rate_limit_storage": "redis",
        "ai_framework": "none",
        "enable_logfire": INACTIVE,
        "enable_cors": False,
        "enable_docker": False,
        "reverse_proxy": INACTIVE,
        "ci_type": "none",
    },
    "sqlmodel_memory": {
        "database": "postgresql",
        "orm_type": "sqlmodel",
        "include_example_crud": False,
        "background_tasks": "none",
        "enable_redis": True,
        "enable_caching": False,
        "enable_rate_limiting": True,
        "rate_limit_storage": "memory",
        "ai_framework": "pydantic_ai",
        "enable_logfire": False,
        "enable_cors": False,
        "enable_docker": True,
        "reverse_proxy": "none",
        "ci_type": "none",
    },
    "taskiq_memory_delivery": {
        "database": "none",
        "orm_type": INACTIVE,
        "include_example_crud": INACTIVE,
        "background_tasks": "taskiq",
        "enable_redis": False,
        "enable_caching": False,
        "enable_rate_limiting": True,
        "rate_limit_storage": "memory",
        "ai_framework": "none",
        "enable_logfire": INACTIVE,
        "enable_cors": True,
        "enable_docker": True,
        "reverse_proxy": "none",
        "ci_type": "github",
    },
    "sqlmodel_cache_no_rate_limit": {
        "database": "postgresql",
        "orm_type": "sqlmodel",
        "include_example_crud": True,
        "background_tasks": "taskiq",
        "enable_redis": True,
        "enable_caching": True,
        "enable_rate_limiting": False,
        "rate_limit_storage": INACTIVE,
        "ai_framework": "pydantic_ai",
        "enable_logfire": False,
        "enable_cors": True,
        "enable_docker": False,
        "reverse_proxy": INACTIVE,
        "ci_type": "github",
    },
    "sqlalchemy_item_memory_nginx": {
        "database": "postgresql",
        "orm_type": "sqlalchemy",
        "include_example_crud": True,
        "background_tasks": "none",
        "enable_redis": False,
        "enable_caching": False,
        "enable_rate_limiting": True,
        "rate_limit_storage": "memory",
        "ai_framework": "none",
        "enable_logfire": INACTIVE,
        "enable_cors": False,
        "enable_docker": True,
        "reverse_proxy": "nginx_external",
        "ci_type": "none",
    },
    "sqlalchemy_cache_memory": {
        "database": "postgresql",
        "orm_type": "sqlalchemy",
        "include_example_crud": False,
        "background_tasks": "none",
        "enable_redis": True,
        "enable_caching": True,
        "enable_rate_limiting": True,
        "rate_limit_storage": "memory",
        "ai_framework": "none",
        "enable_logfire": INACTIVE,
        "enable_cors": False,
        "enable_docker": False,
        "reverse_proxy": INACTIVE,
        "ci_type": "github",
    },
    "redis_rate_limit_agent_nginx": {
        "database": "none",
        "orm_type": INACTIVE,
        "include_example_crud": INACTIVE,
        "background_tasks": "none",
        "enable_redis": True,
        "enable_caching": False,
        "enable_rate_limiting": True,
        "rate_limit_storage": "redis",
        "ai_framework": "pydantic_ai",
        "enable_logfire": False,
        "enable_cors": True,
        "enable_docker": True,
        "reverse_proxy": "nginx_external",
        "ci_type": "none",
    },
    "sqlalchemy_taskiq_no_consumers": {
        "database": "postgresql",
        "orm_type": "sqlalchemy",
        "include_example_crud": False,
        "background_tasks": "taskiq",
        "enable_redis": False,
        "enable_caching": False,
        "enable_rate_limiting": False,
        "rate_limit_storage": INACTIVE,
        "ai_framework": "pydantic_ai",
        "enable_logfire": False,
        "enable_cors": False,
        "enable_docker": True,
        "reverse_proxy": "none",
        "ci_type": "none",
    },
    "sqlmodel_all_redis_consumers": {
        "database": "postgresql",
        "orm_type": "sqlmodel",
        "include_example_crud": False,
        "background_tasks": "none",
        "enable_redis": True,
        "enable_caching": True,
        "enable_rate_limiting": True,
        "rate_limit_storage": "redis",
        "ai_framework": "none",
        "enable_logfire": INACTIVE,
        "enable_cors": False,
        "enable_docker": True,
        "reverse_proxy": "none",
        "ci_type": "none",
    },
    "sqlmodel_item_agent_memory": {
        "database": "postgresql",
        "orm_type": "sqlmodel",
        "include_example_crud": True,
        "background_tasks": "none",
        "enable_redis": False,
        "enable_caching": False,
        "enable_rate_limiting": True,
        "rate_limit_storage": "memory",
        "ai_framework": "pydantic_ai",
        "enable_logfire": True,
        "enable_cors": False,
        "enable_docker": True,
        "reverse_proxy": "none",
        "ci_type": "none",
    },
}

DEEP_PROFILES = (
    "minimal",
    "default",
    "all_retained_sqlalchemy",
    "all_retained_sqlmodel",
    "agent_logfire",
    "redis_consumers_taskiq",
)


def is_valid_state(state: dict[str, object]) -> bool:
    if state["database"] == "none":
        if state["orm_type"] != INACTIVE or state["include_example_crud"] != INACTIVE:
            return False
    elif state["orm_type"] == INACTIVE or state["include_example_crud"] == INACTIVE:
        return False
    if state["enable_caching"] and not state["enable_redis"]:
        return False
    if (not state["enable_rate_limiting"] and state["rate_limit_storage"] != INACTIVE) or (
        state["enable_rate_limiting"]
        and (
            state["rate_limit_storage"] == INACTIVE
            or (state["rate_limit_storage"] == "redis" and not state["enable_redis"])
        )
    ):
        return False
    if state["ai_framework"] == "none":
        if state["enable_logfire"] != INACTIVE:
            return False
    elif state["enable_logfire"] == INACTIVE:
        return False
    if not state["enable_docker"]:
        return state["reverse_proxy"] == INACTIVE
    return state["reverse_proxy"] != INACTIVE


def all_valid_states() -> list[dict[str, object]]:
    factors = tuple(FACTOR_VALUES)
    return [
        state
        for values in product(*(FACTOR_VALUES[factor] for factor in factors))
        if is_valid_state(state := dict(zip(factors, values, strict=True)))
    ]


def pairs(state: dict[str, object]) -> set[tuple[tuple[str, object], tuple[str, object]]]:
    return {
        ((left, state[left]), (right, state[right]))
        for left, right in combinations(FACTOR_VALUES, 2)
    }


def profile_answers(name: str) -> dict[str, Any]:
    state = PROFILE_STATES[name]
    answers: dict[str, Any] = {
        "project_name": "profile_service",
        "project_slug": "profile_service",
        "project_description": "Profile service",
        "author_name": "Template Maintainer",
        "author_email": "maintainer@example.com",
        "timezone": "UTC",
        "python_version": "3.12",
        "backend_port": 8000,
        "db_pool_size": 5,
        "db_max_overflow": 10,
        "db_pool_timeout": 30,
        "rate_limit_requests": 100,
        "rate_limit_period": 60,
        "include_example_crud": False,
        "enable_logfire": False,
        "deployment_api_key": "change-me-in-production",
    }
    answers.update({key: value for key, value in state.items() if value != INACTIVE})
    return answers
