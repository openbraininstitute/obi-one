from fastapi import FastAPI, HTTPException
from typing import Type, Dict, Any, List
import obi
from fastapi.responses import JSONResponse


def activate_fastapi_app(app: FastAPI):

    for subclass in obi.Form.__subclasses__():
        generate_routes(subclass, app)
    return


# Auto-generate API routes
def generate_routes(model: Type[obi.Form], app: FastAPI):

    # Model is the OBI.Form subclass 
    # i.e. <class 'obi.modeling.simulation.simulations.SimulationsForm'>

    # model_name is the name of the model (i.e. OBI.Form subclass) 
    # in lowercase (i.e. 'simulationsform')
    model_name = model.__name__.lower()

    # if model_name == 'simulationsform':

    
        

    # @app.get("/")
    # async def root():
    #     response = JSONResponse(content={"message": "CORS test"})
    #     response.headers["Access-Control-Allow-Origin"] = "*"  # ✅ Proper way to set headers
    #     return response
    
    # @app.post(f"/{model_name}/generate_grid_scan/")
    @app.post(f"/{model_name}/")
    async def generate_grid_scan(form: model):
        
        print("\ngenerate_grid_scan")

        try:
            grid_scan = obi.GridScan(form=form, output_root=f"../obi_output/fastapi_test/{model_name}/grid_scan")
            grid_scan.generate()
        except Exception as e:
            print(e)

        return {}

    # @app.get("/")  # Define a route for the root path "/"
    # def read_root():
    #     return {"message": "Welcome to the OBI modeling library FastAPI!"}

        # response = JSONResponse(content={"message": "CORS test"})
        # response.headers["Access-Control-Allow-Origin"] = "*"
        # return response


        """
        Misc old
        """

        # current_form: obi.Form = None

        # @app.post(f"/{model_name}/set_form/")
        # async def set_form(form_obi_serialized_json: Dict[str, Any]):
        #     """Send a JSON dictionary of an unspecified type"""

        #     global current_form
        #     current_form = obi.deserialize_obi_object_from_json_data(form_obi_serialized_json)

        #     return


        # @app.post(f"/{model_name}/create_form/") #
        # async def create_form(item: model): # , response_model=model
        #     """Create an item"""
        #     global current_form
        #     current_form = item
        #     return

        # @app.get(f"/{model_name}/schema/")
        # async def get_schema():
        #     """Get schema of the model"""
        #     return model.schema()

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

