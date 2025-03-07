from fastapi import FastAPI, HTTPException
from typing import Type, Dict, Any, List
# from obi.modeling.core.form import Form
import obi

# db: Dict[str, Dict[int, Dict[str, Any]]] = {}

current_form: obi.Form = None

def activate_fastapi_app(app: FastAPI):

    for subclass in obi.Form.__subclasses__():
        generate_routes(subclass, app)
    return


# Auto-generate API routes
def generate_routes(model: Type[obi.Form], app: FastAPI):

    # Model is the OBI.Form subclass 
    # i.e. <class 'obi.modeling.simulation.simulations.SimulationsForm'>
    print(model)

    # model_name is the name of the model (i.e. OBI.Form subclass) 
    # in lowercase (i.e. 'simulationsform')
    model_name = model.__name__.lower()
    print(model_name)

    # Create a new dictionary in the db dictionary with the key as the lowercase model_name
    # if model_name not in db:
    #     db[model_name] = {}



    @app.post(f"/{model_name}/set_form/")
    async def set_form(form_obi_serialized_json: Dict[str, Any]):
        """Send a JSON dictionary of an unspecified type"""

        global current_form
        current_form = obi.deserialize_obi_object_from_json_data(form_obi_serialized_json)

        return


    @app.post(f"/{model_name}/create_form/") #
    async def create_form(item: model): # , response_model=model
        """Create an item"""
        # global current_form
        # current_form = model(**item)
        global current_form
        current_form = item
        return

    @app.get(f"/{model_name}/schema/")
    async def get_schema():
        """Get schema of the model"""
        return model.schema()

    @app.post(f"/{model_name}/generate_grid_scan/")
    async def generate_grid_scan():
        """Call generate method on an item by ID"""

        print("\ngenerate_grid_scan")

        # print(current_form)
        grid_scan = obi.GridScan(form=current_form, output_root='../obi_output/fastapi_test/circuit_simulations/grid_scan')
        grid_scan.generate()

        # return {}


        # return grid_scan


            # if item_id not in db[model_name]:
        #     raise HTTPException(status_code=404, detail="Item not found")
        # item_data = db[model_name][item_id]

        # item = model(**item_data)
        # print(item.__class__)


    # @app.get(f"/{model_name}/obi_class_serialization/")
    # async def get_obi_class_serialization():
    #     """Get obi class serialization"""
    #     return model.serialize()

    # @app.get(f"/{model_name}/pythonic_schema/") # , response_model=model
    # async def get_pythonic_schema():
    #     """Get pythonic schema"""
    #     # print(model)
    #     return model.get_pythonic_schema()
    #     # model.get_pythonic_schema()
    #     # return item.get_pythonic_schema()


    



    # # @app.get(f"/{model_name}/{{item_id}}", response_model=model)
    # # async def get_item(item_id: int):
    # #     """Get an item by ID"""
    # #     if item_id not in db[model_name]:
    # #         raise HTTPException(status_code=404, detail="Item not found")
    # #     return db[model_name][item_id]

    # # @app.put(f"/{model_name}/{{item_id}}", response_model=model)
    # # async def update_item(item_id: int, item: model):
    # #     """Update an item by ID"""
    # #     if item_id not in db[model_name]:
    # #         raise HTTPException(status_code=404, detail="Item not found")
    # #     db[model_name][item_id] = item.dict()
    # #     return item

    # # @app.delete(f"/{model_name}/{{item_id}}")
    # # async def delete_item(item_id: int):
    # #     """Delete an item by ID"""
    # #     if item_id not in db[model_name]:
    # #         raise HTTPException(status_code=404, detail="Item not found")
    # #     del db[model_name][item_id]
    # #     return {"message": "Item deleted"}

