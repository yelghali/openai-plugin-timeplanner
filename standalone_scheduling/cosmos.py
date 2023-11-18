from azure.cosmos import CosmosClient, PartitionKey, exceptions
from dotenv import load_dotenv
import os
import json
import random, string

load_dotenv()

url = os.environ["AZURE_COSMOS_ENDPOINT"]
key = os.environ["AZURE_COSMOS_API_KEY"]

client = CosmosClient(url, credential=key)

def randomword(length):
   letters = string.ascii_lowercase
   return ''.join(random.choice(letters) for i in range(length))

def read(container_name):

    database_name = 'healthplanner'
    container = client.get_database_client(database_name).get_container_client(container_name)
    items = list(container.query_items(
        query="SELECT * FROM c",
        enable_cross_partition_query=True
    ))
    
    return items

def write(json_object, container_name):

    database_name = 'healthplanner'
    container = client.get_database_client(database_name).get_container_client(container_name)
    container.upsert_item(json_object)
    # print("Wrote to Cosmos DB")

# with open('data/negotiable_constraints.json') as f:
#     constraints = json.load(f)
# for constraint in constraints:
#     constraint['id'] = randomword(10)
#     print(constraint)
#     write(constraint, 'negotiable_constraints')

def create_container(database_name, container_name):

    database = client.get_database_client(database_name)
    partition_key = PartitionKey(path='/id', kind='Hash')

    try:
        database.create_container(id=container_name, partition_key=partition_key)
        # print('Container \'{0}\' created.'.format(container_name))

    except exceptions.CosmosResourceExistsError:
        print("Container \'{0}\' can't be created because it already exists".format(container_name))

# create_container('healthplanner', 'schedule_diff_to_add')

def delete_container(database_name, container_name):

    database = client.get_database_client(database_name)
    try:
        database.delete_container(container_name)
        # print('Container \'{0}\' was deleted.'.format(container_name))

    except exceptions.CosmosResourceNotFoundError:
        print("Container \'{0}\' can't be deleted because it does not exist.".format(container_name))

# delete_container('healthplanner', 'schedule_diff_to_add')

def empty_container(database_name, container_name):

    delete_container(database_name, container_name)
    create_container(database_name, container_name)

# empty_container('healthplanner', 'schedule_diff_to_add')

