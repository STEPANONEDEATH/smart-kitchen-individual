import json, os, re, urllib.request
from recommend import norm_name, convert

KINDS=('название','порции','ингредиент','время','температура','правило','действие','посуда','шум')
SYSTEM=('Извлеки из текста рецепта факты для базы знаний и верни только JSON-массив объектов без пояснений. '
        'Поля объекта: "kind", "value", "fragment" (исходная строка текста дословно). '
        'Допустимые kind и формат value: "название" — строка; "порции" — целое число; '
        '"ингредиент" — {"name": строка, "quantity": число, "unit": "кг"|"г"|"мл"|"л"|"шт"}; '
        '"время" — число минут; "температура" — число градусов; "правило" — {"если": строка, "то": строка}; '
        '"действие" — строка шага; "посуда" — строка; "шум" — строка, не относящаяся к рецепту. '
        'Не выдумывай фактов, которых нет в тексте; числа переписывай без изменений. '
        'Пример ответа: [{"kind":"название","value":"Каша","fragment":"Название: Каша"},'
        '{"kind":"ингредиент","value":{"name":"овсянка","quantity":100,"unit":"г"},"fragment":"овсянка 100 г"},'
        '{"kind":"правило","value":{"если":"смесь закипела","то":"варите 10 минут"},"fragment":"Если смесь закипела, то варите 10 минут"}]')
def chat(text):
    base=os.environ.get('KITCHEN_LLM_BASE_URL','http://localhost:11434/v1').rstrip('/')
    model=os.environ.get('KITCHEN_LLM_MODEL','qwen2.5:3b-instruct')
    body=json.dumps({'model':model,'temperature':0,'max_tokens':8192,'messages':[{'role':'system','content':SYSTEM},{'role':'user','content':'Текст:\n'+text}]}).encode()
    headers={'Content-Type':'application/json'}
    key=os.environ.get('KITCHEN_LLM_API_KEY')
    if key: headers['Authorization']='Bearer '+key
    try:
        with urllib.request.urlopen(urllib.request.Request(base+'/chat/completions',data=body,headers=headers),timeout=120) as r: out=json.load(r)
    except Exception as e: raise RuntimeError('Сервис LLM недоступен ('+base+'): '+str(e)) from e
    try: content=out['choices'][0]['message']['content']
    except (KeyError,IndexError,AttributeError,TypeError) as e: raise RuntimeError('Неожиданный ответ сервиса: '+json.dumps(out,ensure_ascii=False)[:300]) from e
    if not content or not content.strip(): raise RuntimeError('Модель вернула пустой ответ (finish_reason='+str(out.get('choices',[{}])[0].get('finish_reason'))+')')
    return content,model
def extract_neural(text):
    content,model=chat(text)
    m=re.search(r'\[.*\]',content,re.S)
    if not m: raise RuntimeError('Модель вернула ответ без JSON-массива: '+content[:200])
    lines=[x.strip() for x in re.split(r'[\n;]+',text) if x.strip()]; facts=[]
    for item in json.loads(m.group(0)):
        if not isinstance(item,dict) or item.get('kind') not in KINDS: continue
        kind=item['kind']; value=item.get('value'); fragment=next((l for l in lines if item.get('fragment') and item['fragment'] in l),str(item.get('fragment') or ''))
        try:
            if kind=='ингредиент':
                q,u=convert(float(value['quantity']),str(value['unit']))
                if q<=0: continue
                value=json.dumps({'name':norm_name(str(value['name'])),'quantity':q,'unit':u},ensure_ascii=False)
            elif kind in ('порции','время','температура'):
                v=float(value); value=str(int(v)) if v==int(v) else str(v)
            elif kind=='правило': value=json.dumps({'если':str(value['если']),'то':str(value['то'])},ensure_ascii=False)
            else: value=str(value)
        except (KeyError,TypeError,ValueError): continue
        facts.append({'kind':kind,'value':value,'fragment':fragment,'confidence':None})
    # единицы и названия нормализуются как в эвристиках, чтобы конфликты сравнивались в одном пространстве значений
    return facts,model
