from fastapi import FastAPI
from routers.wellknown import wellknown
from fastapi.middleware.cors import CORSMiddleware
import json

# module imports
from pysat.solvers import Solver
from pysat.card import *
import pathlib
from datetime import date
import json


from pydantic import BaseModel
from azure.cosmos import CosmosClient, PartitionKey, exceptions

import sys
sys.path.insert(1, './standalone_scheduling')
from standalone_scheduling.solve import *
from standalone_scheduling.cosmos import *
from standalone_scheduling.utilities import *
from standalone_scheduling import utilities

app = FastAPI()
app.include_router(wellknown)
app.add_middleware(CORSMiddleware, allow_origins=["https://chat.openai.com"])


# Define the data model
class Availability(BaseModel):
    id : str
    date: str
    employeesAvailabilities: list[dict]



# Initialize Cosmos Client

from dotenv import load_dotenv
load_dotenv()

url = os.environ["AZURE_COSMOS_ENDPOINT"]
key = os.environ["AZURE_COSMOS_API_KEY"]

client = CosmosClient(url, credential=key)

# @app.post("/setEmployeeTimeAvailabilities", summary="Set Employee Time constraints and availabilities", operation_id="setEmployeeTimeAvailabilities")
# async def set_employee_time_availabilities(body: Availability):
#     """
#     Sets Employee Availabilities on a given days. 
#     FOR COPILOT : When calling the APi use a schema similar to 
#     {

#                 "id": "2023-11-12-day", # 2 shifts possible : day or night or both

#                 "date": "2023-11-12-day", # 2 shifts possible : day or night or both

#                 "employeesAvailabilities": [
#                         {
#                         "id": "vivien.londe@microsoft.com",
#                         "available": "true"
#                         },
#                         {
#                         "id": "yassine.el.ghali@microsoft.com",
#                         "available": "true"
#                         }
#                     ]
                
#             }   
#     """
    
#     # Get the Cosmos DB container
#     database_name = 'healthplanner'
#     container_name = 'people-constraints'
#     container = client.get_database_client(database_name).get_container_client(container_name)

#     # Upsert the data
#     container.upsert_item(body.dict())

#     return "Availability updated successfully."





# @app.get("/getEmployeeTimeAvailabilities", summary="Get Employee Time constraints and availabilities", operation_id="getEmployeeTimeAvailabilities")
# async def get_employee_time_availabilities(query: str = None ):
#     """
#     Gets Employee Availabilities on a given days
#     """
#     if query:
#         keywords = query.lower().split()
    
    
#     # Get the Cosmos DB container
#     database_name = 'healthplanner'
#     container_name = 'people-constraints'
#     container = client.get_database_client(database_name).get_container_client(container_name)

#     # Query the Cosmos DB
#     items = list(container.query_items(
#         query="SELECT * FROM c",
#         enable_cross_partition_query=True
#     ))

#     return items



######## API ########

# Define the data model
class Constraint(BaseModel):
    # def __init__(self,
    #              staff_name: str,
    #              calendar_or_relative: str,
    #              date: str,
    #              time: str,
    #              id: str=None):
    #     self.staff_name = staff_name
    #     self.calendar_or_relative = calendar_or_relative
    #     self.date = date
    #     self.time = time
    #     self.id = id
    
    staff_name: str
    calendar_or_relative: str
    date: str
    time: str
    id: str

class ScheduleChange(BaseModel):
    # def __init__(self,
    #              id: str,
    #              staff_name: str,
    #              date: str,
    #              time: str,
    #              to_add: bool,
    #              validated: bool=False):
    #     self.id = id
    #     self.staff_name = staff_name
    #     self.date = date
    #     self.time = time
    #     self.to_add = to_add
    #     self.validated = validated

    staff_name: str
    validated: bool
    date: str
    time: str
    id: str



@app.get("/getScheduleChanges", summary="Propose schedule updates to satisfy constraints", operation_id="getScheduleChanges")
def write_schedule_diffs(query: str = None):
    """
    Constraints are read from the Cosmos DB container 'negotiable_constraints'.
    The schedule is read from the Cosmos DB container 'schedule'.
    A new schedule is proposed by adding and removing items from the schedule.
    The items to add are written to the Cosmos DB container 'schedule_diff_to_add'.
    The items to remove are written to the Cosmos DB container 'schedule_diff_to_remove'.
    """

    old_schedule = cosmos.read('schedule')
    old_model = schedule_as_model(old_schedule, n_staff, n_shifts, staff_dict)
    to_add, to_remove = write_model_diff_to_cosmos(old_model)

    return to_add, to_remove

@app.post("/addConstraint", summary="Add a constraint", operation_id="addConstraint")
def update_constaints(body: Constraint):
    """
    Add a constraint to the Cosmos DB container 'negotiable_constraints'.
    Use the following json for request :
      {
        "id" : "12321", #random string
        "staff_name": "Bob",
        "calendar_or_relative": "calendrier",
        "date": "2023-11-15",
        "time": "day"  # day or night
    }

    """
    constraint = {'staff_name': body.staff_name, 'calendar_or_relative': body.calendar_or_relative, 'date': body.date, 'time': body.time, 'id': cosmos.randomword(10)}    
    cosmos.write(constraint, 'negotiable_constraints')
    # TODO: check if constraint is already in the container and if so, do not add it again.
    return "schedule updated"

# body = Constraint(staff_name='Alice', calendar_or_relative='calendar', date='2021-05-01', time='day')
# update_constaints(body)

@app.post("/validateChange", summary="Validate a change", operation_id="validateChange")
def validate_change(body: ScheduleChange):
    """
    Validate a change by updating one of the Cosmos DB containers 'schedule_diff_to_add' or 'schedule_diff_to_remove'.

    Use the following json body request :

      {
        "id" : "12321",
        "staff_name": "Bob",
        "date": "2023-11-15",
        "time": "day"  # day or night
    }
    """
    if body.to_add:
        change = {'id': body.id, 'staff_name': body.staff_name, 'date': body.date, 'time': body.time, 'validated': True}
        cosmos.write(change, 'schedule_diff_to_add')
        return "Change validated"
    else:
        return "nothing to add."

# body = ScheduleChange(id='1', staff_name='Alice', date='2021-05-01', time='day', to_add=True)
# validate_change(body)

@app.get("/getSchedule", summary="Get the schedule", operation_id="getSchedule")
def get_schedule(query: str = None):
    """
    Get the schedule from the Cosmos DB container 'schedule'.
    If all diffs are validated, update the schedule first.
    """
    to_add = cosmos.read('schedule_diff_to_add')
    to_remove = cosmos.read('schedule_diff_to_remove')
    old_schedule = cosmos.read('schedule')

    if len(to_add) == 0 and len(to_remove) == 0:
        return old_schedule
    
    else:
        model = schedule_as_model(old_schedule, n_staff, n_shifts, staff_dict)
        for change_to_add in to_add:
            if not change_to_add.validated:
                raise Exception('not all changes are validated')
            else:
                binary_variable_index = compute_binary_variable_index(change_to_add.staff_name, change_to_add.date, change_to_add.time)
                model[binary_variable_index-1] = binary_variable_index
        for change_to_remove in to_remove:
            if not change_to_remove.validated:
                raise Exception('not all changes are validated')
            else:
                binary_variable_index = compute_binary_variable_index(change_to_remove.staff_name, change_to_remove.date, change_to_remove.time)
                model[binary_variable_index-1] = -binary_variable_index

        new_schedule = model_as_schedule(model, n_staff, staff_inverted_dict)
        return new_schedule
