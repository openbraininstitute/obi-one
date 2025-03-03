from fastapi import FastAPI, HTTPException
from typing import Type, Dict, Any, List
from obi.modeling.core.form import Form

db: Dict[str, Dict[int, Dict[str, Any]]] = {}

def activate_fastapi_app(app: FastAPI):

    for subclass in Form.__subclasses__():
        print(subclass)
        generate_routes(subclass, app)
        return

# Auto-generate API routes
def generate_routes(model: Type[Form], app: FastAPI):

    print(model)

    model_name = model.__name__.lower()
    if model_name not in db:
        db[model_name] = {}

    @app.post(f"/{model_name}/", response_model=model)
    async def create_item(item: model):
        """Create an item"""
        # db[model_name][item.id] = item.dict()
        # print(item)
        return item
    
    @app.get(f"/{model_name}/generate/{{item_id}}", response_model=model)
    async def call_generate(item_id: int):
        """Call generate method on an item by ID"""
        # if item_id not in db[model_name]:
        #     raise HTTPException(status_code=404, detail="Item not found")
        item_data = db[model_name][item_id]

        item = model(**item_data)
        print(item.__class__)
        print(item.generate())
        return item


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

