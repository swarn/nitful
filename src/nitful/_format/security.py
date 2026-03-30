from typing import Any

from nitful._dsl.spec import EcsString, EcsStringEnum, Spec
from nitful.core.common import SecurityClass

# TODO: Maybe this should be a DataclassRecord, wrather than wrapping it in
# same everywhere.
security_spec: list[Spec[Any]] = [
    EcsStringEnum("SCLAS", 1, enum=SecurityClass),
    EcsString("SCLSY", 2),
    EcsString("SCODE", 11),
    EcsString("SCTLH", 2),
    EcsString("SREL", 20),
    EcsString("SDCTP", 2),
    EcsString("SDCDT", 8),
    EcsString("SDCXM", 4),
    EcsString("SDG", 1),
    EcsString("SDGDT", 8),
    EcsString("SCLTX", 43),
    EcsString("SCATP", 1),
    EcsString("SCAUT", 40),
    EcsString("SCRSN", 1),
    EcsString("SSRDT", 8),
    EcsString("SCTLN", 15),
]
