# module imports
from pysat.solvers import Solver
from pysat.card import *
import pathlib
from datetime import date
import json

from fastapi import FastAPI
# from routers.wellknown import wellknown
from fastapi.middleware.cors import CORSMiddleware
 
app = FastAPI()
# app.include_router(wellknown)
app.add_middleware(CORSMiddleware, allow_origins=["https://chat.openai.com"])

# Define the data model
class Constraint():
    def __init__(self,
                 staff_name: str,
                 calendar_or_relative: str,
                 date: str,
                 time: str,
                 id: str=None):
        self.staff_name = staff_name
        self.calendar_or_relative = calendar_or_relative
        self.date = date
        self.time = time
        self.id = id

class ScheduleChange():
    def __init__(self,
                 id: str,
                 staff_name: str,
                 date: str,
                 time: str,
                 to_add: bool,
                 validated: bool=False):
        self.id = id
        self.staff_name = staff_name
        self.date = date
        self.time = time
        self.to_add = to_add
        self.validated = validated

# local imports
import cosmos
from utilities import binary_variable_encoding, binary_variable_decoding
from utilities import days_between, compute_distance, date_and_time_as_string
from utilities import write_to_excel, model_as_schedule, schedule_as_model
from utilities import compute_binary_variable_index


parent_path = pathlib.Path(__file__).parent.resolve()

n_staff = 5 # 1 <=_staff_index <= n_staff
n_shifts = 4 # 0 <= shift_index <= n_shifts-1
top_id = n_staff * n_shifts

staff_dict = {'Alice' : 1, 'Bob' : 2, 'Charlie' : 3, 'David' : 4, 'Eve' : 5}
staff_inverted_dict = {str(value) : key for key, value in staff_dict.items()}

def service_constraint(shift_index):
    # use top_id to ensure that auxiliary variables are given new indices
    cnfplus = CNFPlus()
    if shift_index % 2 == 0: # day shift
        nb_staff_required = 3
    else: # night shift
        nb_staff_required = 1
    literals = [binary_variable_encoding(shift_index, staff_index, n_staff) for staff_index in range(1, n_staff+1)]
    # print("service constraints literals:", literals)
    cnfplus.append([literals, nb_staff_required], is_atmost=True) # = CardEnc.equals(lits=literals, bound=nb_staff_required)
    cnfplus.append([[-x for x in literals], len(literals) - nb_staff_required], is_atmost=True) # implements an at_least constraitn
    # overall we have implemented an is_equal constraint 
    return cnfplus

def sliding_window_constraint(staff_index, sliding_window_size, bound):
    # print("new sw constraint")
    cnfplus = CNFPlus()
    for first_shift_index in range(n_shifts-sliding_window_size+1):
        # print('fsi:', first_shift_index)
        literals = [binary_variable_encoding(first_shift_index + t, staff_index, n_staff) for t in range(sliding_window_size) if first_shift_index + t <= n_shifts-1]
        # print("sliding window literals:", literals)
        cnfplus.append([literals, bound], is_atmost=True) # cnfplus.atmost(literals, bound, top_id) # cnfplus.append(CardEnc.equals(lits=literals, bound=bound))
    return cnfplus

def retrieve_negotiable_constraints(filename):

    negotiable_constraints = []

    with open(parent_path / filename, 'r') as f:
        constraints_as_list_of_dict = json.load(f)

    for constraint_as_dict in constraints_as_list_of_dict:
        staff_index = staff_dict[constraint_as_dict['staff_name']]
        # print(constraint_as_dict['staff_name'])

        if constraint_as_dict['calendar_or_relative'] in ['calendar', 'calendrier']:
            today = str(date.today())
            h24_index = days_between(today, constraint_as_dict['date'])
            h12_index = h24_index * 2
        elif constraint_as_dict['calendar_or_relative'] in ['relative', 'relatif']:
            relative_date = {'demain' : 1, 'tomorrow' : 1, 'après-demain' : 2, 'day after tomorrow' : 2, 'la semaine prochaine' : 7, 'next week' : 7, 'le mois prochain' : 30, 'next month' : 30}
            h24_index = relative_date[constraint_as_dict['date']]
            h12_index = h24_index * 2
        else:
            print('Error: calendar_or_relative should be either calendar or relative')
        # print('first_h12_index:', h12_index)

        if constraint_as_dict["time"] in ['night', 'nuit']:
            h12_index += 1
        elif constraint_as_dict["time"] in ['day', 'jour']:
            pass
        else:
            print('Error: day_or_night should be either day or night')
        # print('second_h12_index:', h12_index)

        binary_variable_index = binary_variable_encoding(h12_index, staff_index, n_staff)
        negotiable_constraints.append([-binary_variable_index])

    return negotiable_constraints

def get_permanent_constraints():

    formula = CNFPlus()

    # print('retrieving permanent constraints..')
    for shift_index in range(n_shifts):
        formula.extend(service_constraint(shift_index))

    for staff_index in range(1, n_staff+1):
        formula.extend(sliding_window_constraint(staff_index, 14, 4)) # no more than 4 shifts in a week
        formula.extend(sliding_window_constraint(staff_index, 7, 3)) # no more than 3 day-consecutive or night-consecutive shifts
        formula.extend(sliding_window_constraint(staff_index, 2, 1)) # no 24h in a row shifts

    return formula

def find_closest_model(solver, formula, old_model):
    smallest_distance = n_shifts * n_staff # initialize with a large value
    new_model = None
    nb_models = 0
    with Solver(name=solver, bootstrap_with=formula, warm_start=True) as oracle:
        while oracle.solve() and smallest_distance > 2:
            candidate_model = oracle.get_model()
            d = compute_distance(candidate_model, old_model)
            if d < smallest_distance:
                # print('Old smallest distance:', smallest_distance, '. New smallest distance:', d)
                smallest_distance = d
                new_model = candidate_model
                # print(new_model)
            oracle.add_clause([-l for l in new_model])
            nb_models += 1
            # if nb_models%10 == 0:
            #     print('number of satisfying models found:', nb_models)
            #     print(candidate_model)
    return new_model, smallest_distance

def add_negotiable_constraints_and_solve(formula):
    negotiable_constraints = retrieve_negotiable_constraints('data/negotiable_constraints.json')
    formula.extend(negotiable_constraints)
    # print('negotiable constraints:', formula.clauses)
    solver.append_formula(formula)
    # print('computing a solution schedule..')
    solver.solve()
    return solver.get_model()

def write_model_to_cosmos(model):
    schedule = model_as_schedule(model, n_staff, staff_inverted_dict)
    # with open('data/schedule.json', 'w') as f:
    #     json.dump(schedule, f, indent=4)
    cosmos.empty_container('healthplanner', 'schedule')
    for item in schedule:
        cosmos.write(item, 'schedule')

def compute_new_model(old_model):

    formula_additional_negotiable_constraints = retrieve_negotiable_constraints('data/additional_negotiable_constraints.json')
    print('additional negotiable constraints:', formula_additional_negotiable_constraints)
    formula_negotiable_constraints.extend(formula_additional_negotiable_constraints)
    formula_to_solve = formula_permanent_constraints.copy()
    formula_to_solve.extend(formula_negotiable_constraints)
    new_model, distance = find_closest_model('minicard', formula_to_solve, old_model)
    return new_model    

def write_model_diff_to_cosmos(old_model):

    new_model = compute_new_model(old_model)
    to_add = []
    to_remove = []
    cosmos.empty_container('healthplanner', 'schedule_diff_to_add')
    cosmos.empty_container('healthplanner', 'schedule_diff_to_remove')
    for old_v, new_v in zip(old_model, new_model):
        shift_index, staff_index = binary_variable_decoding(abs(old_v), n_staff)
        calendar_date, time = date_and_time_as_string(shift_index)
        item = {"id": str(abs(old_v)),
                "staff_name": staff_inverted_dict[str(staff_index)],
                "date": calendar_date,
                "time": time,
                "validated": False}
        if old_v * new_v < 0: # w and w have opposite sign when they disagree
            if new_v > 0:
                to_add.append(item)
                cosmos.write(item, 'schedule_diff_to_add')  
            else:
                to_remove.append(item)
                cosmos.write(item, 'schedule_diff_to_remove')
    # with open('data/diff.json', 'w') as f:
    #     json.dump({'to_add': to_add, 'to_remove': to_remove}, f, indent=4)
    
    return to_add, to_remove


######## API ########

# @app.get("/getScheduleChanges", summary="Propose schedule updates to satisfy constraints", operation_id="getScheduleChanges")
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

# @app.post("/addConstraint", summary="Add a constraint", operation_id="addConstraint")
def update_constaints(body: Constraint):
    """
    Add a constraint to the Cosmos DB container 'negotiable_constraints'.
    """
    constraint = {'staff_name': body.staff_name, 'calendar_or_relative': body.calendar_or_relative, 'date': body.date, 'time': body.time, 'id': cosmos.randomword(10)}    
    cosmos.write(constraint, 'negotiable_constraints')
    # TODO: check if constraint is already in the container and if so, do not add it again.

# body = Constraint(staff_name='Alice', calendar_or_relative='calendar', date='2021-05-01', time='day')
# update_constaints(body)

# @app.post("/validateChange", summary="Validate a change", operation_id="validateChange")
def validate_change(body: ScheduleChange):
    """
    Validate a change by updating one of the Cosmos DB containers 'schedule_diff_to_add' or 'schedule_diff_to_remove'.
    """
    if body.to_add:
        change = {'id': body.id, 'staff_name': body.staff_name, 'date': body.date, 'time': body.time, 'validated': True}
        cosmos.write(change, 'schedule_diff_to_add')

# body = ScheduleChange(id='1', staff_name='Alice', date='2021-05-01', time='day', to_add=True)
# validate_change(body)

# @app.get("/getSchedule", summary="Get the schedule", operation_id="getSchedule")
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

# new_schedule = get_schedule()
# print(new_schedule)








# if __name__=='__main__':
    
#     formula_permanent_constraints = get_permanent_constraints()

#     formula_negotiable_constraints = retrieve_negotiable_constraints('data/negotiable_constraints.json')
#     formula_to_solve = formula_permanent_constraints.copy()
#     formula_to_solve.extend(formula_negotiable_constraints)
#     print('original negotiable constraints', formula_to_solve.clauses)
#     with Solver('minicard', bootstrap_with=formula_to_solve) as solver:
#         if solver.solve():
#             old_model = solver.get_model()
#         else:
#             raise Exception('impossible to satisfy all constraints')
#     print('old_model:', old_model)
#     write_model_to_cosmos(old_model)
#     write_to_excel(old_model, formula_negotiable_constraints, 'data/schedule.xlsx', n_staff)

#     write_model_diff_to_cosmos(old_model)
    


























