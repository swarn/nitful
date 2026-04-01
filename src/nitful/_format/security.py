from nitful._dsl.spec import DataclassRecord, EcsString, EcsStringEnum
from nitful.core import Security
from nitful.core.common import SecurityClass

security_spec = DataclassRecord(
    name="security",
    model_cls=Security,
    specs=[
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
    ],
)

security_len = 167
