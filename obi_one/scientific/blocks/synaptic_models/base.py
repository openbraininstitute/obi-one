from pandas import DataFrame

from obi_one.core.block import Block
from obi_one.scientific.blocks import distributions


def _default_tm():
    from obi_one.scientific.blocks.synaptic_models.tsodyks_markram import (
        TsodyksMarkramSynapticModel,
    )
    from obi_one.scientific.unions.unions_distributions import AllDistributionsReference

    params_dict = {}

    def make_reference_and_add(param, distribution_obj):
        tmp_ref = AllDistributionsReference(block_dict_name="Distribution", block_name=param)
        tmp_ref.block = distribution_obj
        params_dict[param] = tmp_ref

    make_reference_and_add(
        "u_hill_coefficient_distribution", distributions.FloatConstantDistribution(value=1.94)
    )
    make_reference_and_add(
        "conductance_distribution", distributions.GammaDistribution(shape=4.0, scale=0.25)
    )
    make_reference_and_add(
        "conductance_scale_factor_distribution", distributions.FloatConstantDistribution(value=0.7)
    )
    make_reference_and_add(
        "fascilitation_time", distributions.GammaDistribution(shape=11.56, scale=1.4706)
    )
    make_reference_and_add(
        "depression_time", distributions.GammaDistribution(shape=1995.11, scale=0.3358)
    )
    make_reference_and_add(
        "n_rrp_vesicles_distribution",
        distributions.IntDiscreteDistribution(
            values=(1, 2, 3, 4, 5), probabilities=(0.3, 0.3, 0.2, 0.1, 0.1)
        ),
    )
    make_reference_and_add(
        "decay_time",
        distributions.NormalDistribution(min=1.7, max=1.9, mean=1.7, standard_deviation=0.1),
    )
    make_reference_and_add(
        "delay_distribution",
        distributions.NormalDistribution(min=0.1, max=5.0, mean=2.0, standard_deviation=1.0),
    )
    make_reference_and_add(
        "usyn",
        distributions.NormalDistribution(min=0.2, max=0.7, mean=0.5, standard_deviation=0.25),
    )

    return TsodyksMarkramSynapticModel(**params_dict)


_DEFAULTS = {"TM_model": _default_tm}


class SynapticModelBase(Block):
    def parameter_dictionaries(self) -> dict:
        raise NotImplementedError("This is an abstract class!")

    @classmethod
    def synapse_model_family(cls):
        return "NONE"

    @classmethod
    def compatible_with(cls, other) -> None:
        """Tests whether this subclass of SynapticModelBase is compatible
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
        """Returns the names of the synapse parameters provided by this class.
        Important: `SynapticModelBase` classes that share the same
        _synapse_model_family MUST return the same list of parameter names!
        """
        raise NotImplementedError("This is an abstract class!")

    @classmethod
    def default(cls):
        """Provide a version of this class with default parameterization.
        This is guaranteed to be the same or functionally equivalent for all
        subclasses withing the same ._synapse_model_family
        """
        if cls.synapse_model_family() == "NONE":
            raise NotImplementedError("This is an abstract class!")
        return _DEFAULTS[cls.synapse_model_family()]()

    @classmethod
    def from_dict(cls, serialized_dict):
        from obi_one.scientific.blocks import distributions
        from obi_one.scientific.unions.unions_distributions import AllDistributionsReference

        def dist_ref(name: str) -> AllDistributionsReference:
            """Helper to create a distribution reference."""
            return AllDistributionsReference(block_dict_name="distributions", block_name=name)

        assert serialized_dict["class"] == cls.__name__
        distr_obj_dict = {}
        distr_ref_dict = {}
        for param_name, distr_dict in serialized_dict["distributions"].items():
            distr_cls = distr_dict.pop("type")
            distr_obj_dict[param_name] = distributions.__dict__[distr_cls](**distr_dict)
            distr_ref_dict[param_name] = dist_ref(param_name)
            distr_ref_dict[param_name].block = distr_obj_dict[param_name]
        return cls(**distr_ref_dict), distr_obj_dict

    def sample(self, indices: DataFrame) -> DataFrame:
        """The main functionality of this class. Returns synapse parameters as
        specified. The input is a DataFrame with two columns: @source_node
        and @target_node. Its index is the edge index as used in SONATA.
        Returns DataFrame with one named column per parameter and the same index
        as the input.
        """
        raise NotImplementedError("This is an abstract class!")
