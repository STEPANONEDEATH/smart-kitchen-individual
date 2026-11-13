import json, re
from db import connect
from recommend import norm_name, convert
from neural import extract_neural

def extract(text, pipeline='A', neural=False):
    if pipeline not in ('A','B','C'): raise ValueError('Конвейер должен быть A, B или C')
    if not text.strip(): raise ValueError('Текст пуст')
    if pipeline=='C': return extract_neural(text)
    lines=[x.strip() for x in re.split(r'[\n;]+',text) if x.strip()]; facts=[]
    def add(kind,value,fragment): facts.append({'kind':kind,'value':str(value),'fragment':fragment,'confidence':None})
    def entities():
        for line in lines:
            m=re.search(r'^(?:Название|Блюдо):\s*(.+)',line,re.I)
            if m: add('название',m.group(1),line)
            m=re.search(r'(\d+)\s*порц',line,re.I)
            if m: add('порции',m.group(1),line)
            m=re.search(r'^\s*[-•]?\s*([а-яё ]+?)\s*[-—:]?\s*(\d+(?:[.,]\d+)?)\s*(кг|грамм|гр|г|мл|л|шт|штуки|штук)\b',line,re.I)
            if m:
                q,u=convert(float(m.group(2).replace(',','.')),m.group(3)); add('ингредиент',json.dumps({'name':norm_name(m.group(1).strip()),'quantity':q,'unit':u},ensure_ascii=False),line)
            for word in ('кастрюля','сковорода','духовка'):
                if re.search(word[:-1],line.lower()): add('посуда',word,line)
            for m in re.finditer(r'(\d+)\s*(минут\w*|мин\.?|°\s*c|градус\w*)',line,re.I): add('время' if m.group(2).lower().startswith('мин') else 'температура',m.group(1),line)
    def relations():
        for line in lines:
            m=re.search(r'если\s+(.+?),\s*то\s+(.+)',line,re.I)
            if m: add('правило',json.dumps({'если':m.group(1),'то':m.group(2)},ensure_ascii=False),line)
            elif re.search(r'\b(варите|смешайте|добавьте|запекайте|обжарьте|доведите)\b',line,re.I): add('действие',line,line)
            elif re.search(r'история|интересный факт|приятного аппетита',line,re.I): add('шум',line,line)
    # Различие порядка реально влияет на порядок фактов; извлечение независимо.
    (entities(),relations()) if pipeline=='A' else (relations(),entities())
    model='эвристики (без модели)'
    if neural:
        try:
            from transformers import pipeline as hf_pipeline
            classifier=hf_pipeline('zero-shot-classification',model='joeddav/xlm-roberta-large-xnli',local_files_only=True)
            for line in lines:
                pred=classifier(line,candidate_labels=['инструкция приготовления','посторонняя информация'])
                add('классификация модели',json.dumps({'label':pred['labels'][0],'score':pred['scores'][0]},ensure_ascii=False),line)
                facts[-1]['confidence']=float(pred['scores'][0])
            model='joeddav/xlm-roberta-large-xnli (локальный кэш)'
        except Exception as e: raise RuntimeError('Модель недоступна локально. Загрузите её по инструкции или отключите нейросеть. '+str(e)) from e
    return facts,model

def save_extraction(source,text,recipe,pipeline,neural=False):
    facts,model=extract(text,pipeline,neural)
    with connect() as c:
        sid=c.execute('INSERT INTO sources(name,text,recipe_name) VALUES (?,?,?)',(source,text,recipe)).lastrowid
        eid=c.execute('INSERT INTO extractions(source_id,pipeline,model) VALUES (?,?,?)',(sid,pipeline,model)).lastrowid
        for f in facts:
            fid=c.execute('INSERT INTO facts(extraction_id,kind,value,fragment,confidence) VALUES (?,?,?,?,?)',(eid,f['kind'],f['value'],f['fragment'],f['confidence'])).lastrowid
            if f['kind'] not in ('ингредиент','время','температура','правило'): continue
            for old in c.execute('''SELECT f.id,f.value,s.name FROM facts f JOIN extractions e ON e.id=f.extraction_id JOIN sources s ON s.id=e.source_id WHERE s.recipe_name=? COLLATE NOCASE AND f.kind=? AND f.id<>? AND f.status!='отклонено' ''',(recipe,f['kind'],fid)).fetchall():
                a,b=f['value'],old['value']; reason=None
                if f['kind']=='ингредиент':
                    x,y=json.loads(a),json.loads(b)
                    if x['name']==y['name'] and (x['unit']!=y['unit'] or x['quantity']!=y['quantity']): reason='Различаются количество или единицы; проверьте число порций и совместимость единиц.'
                elif f['kind'] in ('время','температура') and a!=b: reason='Различаются значения; проверьте, относится ли факт к одному этапу.'
                elif f['kind']=='правило':
                    x,y=json.loads(a),json.loads(b)
                    if x['если'].lower()==y['если'].lower() and x['то'].lower()!=y['то'].lower(): reason='При одинаковом условии указаны разные действия; проверьте совместимость.'
                if reason: c.execute('INSERT INTO conflicts(fact_id,other_fact_id,explanation) VALUES (?,?,?)',(fid,old['id'],reason+' Источник: '+old['name']))
    return eid
