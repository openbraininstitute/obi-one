import requests
from pydantic import BaseModel
import main

params = {
	'name': "test",
	'id': 1
}
print(requests.post("http://127.0.0.1:8000/circuitsimulation/", json=params).json())
print(requests.get("http://127.0.0.1:8000/circuitsimulation/1").json())
print(requests.get("http://127.0.0.1:8000/circuitsimulation/generate/1").json())