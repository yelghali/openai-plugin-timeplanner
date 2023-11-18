import openai

from env import AZURE_OPENAI_COMPLETION_DEPLOYMENT_NAME as completion_deployment_name
from env import AZURE_OPENAI_ENDPOINT as endpoint
from env import AZURE_OPENAI_API_KEY as api_key

openai.api_type = "azure"
openai.api_key = api_key
openai.api_base = endpoint
openai.api_version = "2023-05-15"

with open('metaprompt.txt', 'r') as f:
    metaprompt = f.read()

separation_str = '\n\n' + '-'*60 + '\n\n'

person_talking = 'Bob'
# user_input = 'Je suis en vacances le 8 novembre pendant la nuit.'
# user_input = 'Je suis en formation demain pendant la journée.'
user_input = input("\nChatbot : \nEst-ce-que vous avez une nouvelle contrainte d'emploi du temps ?\n"
    + "Comme par exemple un congé ou une formation.\n\n"
    + person_talking + " :\n")

prompt = metaprompt + user_input + separation_str
# print(prompt)

response = openai.ChatCompletion.create(engine=completion_deployment_name,
                messages=[{"role": "system", "content": prompt},])

print('\n')

# print(response, '\n')
response = response['choices'][0]['message']['content']
calendar_or_relative, absence_date, day_or_night = response.split("\n")
absence = person_talking + ', ' + calendar_or_relative.lower() + ', ' + absence_date + ', ' + day_or_night.lower() + '\n'

print('Absence inférée par le modèle de langage (GPT):', absence)
with open('individual_constraints.txt', 'a') as f:
    f.write(absence)