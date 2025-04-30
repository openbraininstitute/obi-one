from fastapi import APIRouter

prefix = ""
# prefix = "/neuroagent"

router = APIRouter(prefix=prefix, tags=["OBI-ONE - Neuroagent"])

# Create POST endpoint
@router.post("hello_world", summary="Hello world summary", description="Hello workd description")
async def hello_world():
    return {"message": "Hello world!"}
