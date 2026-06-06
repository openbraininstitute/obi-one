from pandas import DataFrame
from bluepysnap.edges import EdgePopulation

from obi_one.core.block import Block
from obi_one.scientific.blocks.distributions.uniform import FloatUniformDistribution

def _default_tm():
    from obi_one.scientific.blocks.synaptic_models.tsodyks_markram import TsodyksMarkramSynapticModel
    from obi_one.scientific.unions.unions_distributions import AllDistributionsReference
    param_names = [
        "u_hill_coefficient_distribution",
        "conductance_distribution",
        "conductance_scale_factor_distribution",
        "fascilitation_time",
        "depression_time",
        "n_rrp_vesicles_distribution",
        "decay_time",
        "usyn",
        ]
    params_dict = {}
    for param in param_names:  # TODO: Fill in actually sane defaults
        
        tmp_distribution = FloatUniformDistribution(low=0.0, high=1.0)
        tmp_ref = AllDistributionsReference(block_dict_name="Distributions",
                                            block_name=param)
        tmp_ref.block = tmp_distribution
        params_dict[param] = tmp_ref

    return TsodyksMarkramSynapticModel(**params_dict)

_DEFAULTS = {
    "TM_model": _default_tm
}

class SynapticModelBase(Block):
    def parameter_dictionaries(self) -> dict:
        raise NotImplementedError("This is an abstract class!")
    
    @classmethod
    def synapse_model_family(cls):
        return "NONE"
    
    @classmethod
    def compatible_with(cls, other) -> None:
        """
        Tests whether this subclass of SynapticModelBase is compatible
        with another. A required but not sufficient condition is that
        they provide the same list of synapse parameters.
        More generally, compatibility means that the .default of one
        class is functionally identical to the one of the other.
        """
        if cls.synapse_model_family() == "NONE":
            raise ValueError("This is an abstract class!")
        if cls.synapse_model_family() != other.synapse_model_family():
            raise ValueError("Synapse models incompatible!")
        # Below should not be needed. Just to be safe...
        param_names = cls.parameter_names()
        other_names = other.parameter_names()
        for k in param_names:
            if k not in other_names:
                raise ValueError("Internal OBI-ONE error!")
        for k in other_names:
            if k not in param_names:
                raise ValueError("Internal OBI-ONE error!")
    
    @classmethod
    def parameter_names(cls) -> list[str]:
        """
        Returns the names of the synapse parameters provided by this class.
        Important: `SynapticModelBase` classes that share the same 
        _synapse_model_family MUST return the same list of parameter names!
        """
        raise NotImplementedError("This is an abstract class!")
    
    @classmethod
    def default(cls):
        """
        Provide a version of this class with default parameterization.
        This is guaranteed to be the same or functionally equivalent for all
        subclasses withing the same ._synapse_model_family
        """
        if cls.synapse_model_family() == "NONE":
            raise NotImplementedError("This is an abstract class!")
        return _DEFAULTS[cls.synapse_model_family()]()
    
    def sample(self, indices: DataFrame) -> DataFrame:
        """
        The main functionality of this class. Returns synapse parameters as
        specified. The input is a DataFrame with two columns: @source_node
        and @target_node. Its index is the edge index as used in SONATA.
        Returns DataFrame with one named column per parameter and the same index
        as the input.
        """
        raise NotImplementedError("This is an abstract class!")
