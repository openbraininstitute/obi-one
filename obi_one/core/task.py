import abc

from obi_one.core.base import OBIBaseModel


class Task(OBIBaseModel, abc.ABC):
    
    json_schema_extra_additions = {
        "ui_enabled": False,
    }
