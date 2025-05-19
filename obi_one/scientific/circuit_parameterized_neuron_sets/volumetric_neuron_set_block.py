import abc
import pandas
import numpy
from typing import Self

from pydantic import Field, model_validator

from obi_one.core.block import Block


class NeuronPropertyFilterBlock(Block, abc.ABC):

    property_name: str | list[str] = Field(
        name="Property name",
        description="Property name"
    )

    property_values : tuple[str, ...] | list[tuple[str, ...]] = Field(
        name="Property values",
        description="Valid values for the property"
    )

    def filter(self, df_in, reindex=True):
        self.enforce_no_lists()
        vld = df_in[self.property_name].isin(self.property_values)
        ret = df_in.loc[vld]
        if reindex:
            ret = ret.reset_index(drop=True)
        return ret
        

class VolumetricNeuronSetBlock(Block, abc.ABC):
    ox : float | list[float] = Field(
        name="Offset: x",
        description="Offset of the center of the volume, relative to the centroid of the node population"
    )
    oy : float | list[float] = Field(
        name="Offset: y",
        description="Offset of the center of the volume, relative to the centroid of the node population"
    )
    oz : float | list[float] = Field(
        name="Offset: z",
        description="Offset of the center of the volume, relative to the centroid of the node population"
    )
    n : int | list[int] = Field(
        name="Number of neurons",
        description="Number of neurons to find"
    )
    filters : tuple[NeuronPropertyFilterBlock, ...] | list[tuple[NeuronPropertyFilterBlock, ...]] = Field(
        name="Neuron property filters",
        description="Neuron property filters"
    )
    node_population : str | list[str] = Field(
        name="Node population",
        description="The node population to consider"
    )

    def for_circuit(self, circ):
        self.enforce_no_lists()
        required_props = ["x", "y", "z"]
        for fltr in self.filters:
            fltr.enforce_no_lists()
            required_props.append(fltr.property_name)
        
        df = circ.nodes["S1nonbarrel_neurons"].get(properties=required_props).reset_index()

        for fltr in self.filters:
            df = fltr.filter(df)
        
        cols_xyz = ["x", "y", "z"]
        o_df = pandas.Series({
            cols_xyz[0]: self.ox,
            cols_xyz[1]: self.oy,
            cols_xyz[2]: self.oz
        })
        tgt_center = df[cols_xyz].mean() + o_df

        D = numpy.linalg.norm(df[cols_xyz] - tgt_center, axis=1)
        idxx = numpy.argsort(D)[:self.n]
        df = df.iloc[idxx]

        expression = {"population": self.node_population, "node_id": list(df["node_ids"].astype(int))}
        return expression
