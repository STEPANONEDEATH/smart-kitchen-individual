from datetime import date
from collections import defaultdict
from db import connect

ALIASES={'яйца':'яйцо','яиц':'яйцо','томаты':'помидор','томат':'помидор','помидоры':'помидор','овсяные хлопья':'овсянка'}
UNITS={'г':'г','гр':'г','грамм':'г','кг':'кг','мл':'мл','л':'л','шт':'шт','штуки':'шт','штук':'шт'}
def norm_name(s):
    s=' '.join(s.lower().strip().split()); return ALIASES.get(s,s)
def convert(q, unit):
    u=UNITS.get(unit.lower().strip().rstrip('.'))
    if not u: raise ValueError('Неподдерживаемая единица: '+unit)
    if q < 0: raise ValueError('Количество не может быть отрицательным')
    return (q*1000, {'кг':'г','л':'мл'}[u]) if u in ('кг','л') else (q,u)
def recommend(fridges, event, servings, today=None):
    if isinstance(servings,bool) or not isinstance(servings,int) or servings <= 0: raise ValueError('Число порций должно быть положительным целым')
    if not fridges or len(fridges)!=len(set(fridges)): raise ValueError('Выберите хотя бы один холодильник без повторов')
    today=today or date.today(); warnings=[]; inventory=defaultdict(float)
    with connect() as c:
        marks=','.join('?' for _ in fridges)
        if c.execute(f'SELECT count(*) FROM fridges WHERE id IN ({marks})',fridges).fetchone()[0]!=len(fridges): raise ValueError('Холодильник не найден')
        for row in c.execute(f'SELECT s.*,p.name FROM stock s JOIN products p ON p.id=s.product_id WHERE fridge_id IN ({marks})',fridges):
            try:
                if row['expires'] and date.fromisoformat(row['expires']) < today: warnings.append(f"{row['name']}: просрочен, партия исключена"); continue
                if not row['expires']: warnings.append(f"{row['name']}: срок годности неизвестен")
                q,u=convert(row['quantity'],row['unit']); inventory[(row['product_id'],u)]+=q
            except ValueError as e: warnings.append(f"{row['name']}: {e}; партия исключена")
        available={r[0] for r in c.execute(f'SELECT equipment_id FROM fridge_equipment WHERE fridge_id IN ({marks})',fridges)}
        results=[]
        for recipe in c.execute('SELECT r.* FROM recipes r JOIN recipe_events e ON e.recipe_id=r.id WHERE e.event=? ORDER BY r.name',(event,)).fetchall():
            lines=[]; missing=[]
            for item in c.execute('SELECT i.*,p.name FROM ingredients i JOIN products p ON p.id=i.product_id WHERE recipe_id=?',(recipe['id'],)):
                q,u=convert(item['quantity']*servings/recipe['servings'],item['unit']); have=inventory[(item['product_id'],u)]; shortage=max(0,q-have)
                lines.append({'product':item['name'],'need':q,'have':have,'unit':u,'missing':shortage})
            for e in c.execute('SELECT e.id,e.name FROM recipe_equipment re JOIN equipment e ON e.id=re.equipment_id WHERE recipe_id=?',(recipe['id'],)):
                if e['id'] not in available: missing.append(e['name'])
            food=any(x['missing']>1e-9 for x in lines)
            status=('не хватает продуктов и принадлежностей' if food and missing else 'не хватает продуктов' if food else 'не хватает кухонных принадлежностей' if missing else 'можно приготовить')
            results.append({'id':recipe['id'],'name':recipe['name'],'status':status,'ingredients':lines,'equipment_missing':missing})
        return results,list(dict.fromkeys(warnings))
def shopping(fridges,event,servings,recipe_ids):
    results,_=recommend(fridges,event,servings); chosen=[r for r in results if r['id'] in recipe_ids]
    if not chosen or len(chosen)!=len(set(recipe_ids)): raise ValueError('Выберите блюда из рекомендаций')
    total={}
    for recipe in chosen:
        for x in recipe['ingredients']:
            key=(x['product'],x['unit']); v=total.setdefault(key,{'need':0,'have':x['have']}); v['need']+=x['need']
    return [{'product':k[0],'unit':k[1],'quantity':max(0,v['need']-v['have'])} for k,v in total.items() if v['need']>v['have']+1e-9]
