import json
data = json.load(open('data/agentes.json', 'r', encoding='utf-8'))
agentes = data['agentes']
print(f"Total: {len(agentes)}\n")
for i, a in enumerate(agentes):
    m = a['metadata']
    print(f"{i+1}. {m['nombre']}")
    print(f"   Estado: {m['estado']} | Dueno: {m['dueno']}")
    print(f"   ID: {a['id']}")
    print()
