import json
from nlp import extract
CASES=[('Название: Каша\n2 порции\nовсянка 100 г\nЕсли смесь закипела, то варите 10 минут',{'название','порции','ингредиент','правило','время'}),('Название: Рис\nрис 200 г\nДобавьте помидоры\nПриятного аппетита',{'название','ингредиент','действие','шум'}),('Название: Суп\nЕсли закипело, то варите 20 минут\nИстория блюда',{'название','правило','время','шум'}),('Название: Омлет\nяйца 4 шт\nСмешайте яйца\nсковорода',{'название','ингредиент','действие','посуда'})]
for pipeline in ('A','B'):
 tp=fp=fn=0
 for text,gold in CASES:
  facts,_=extract(text,pipeline); predicted={f['kind'] for f in facts}; tp+=len(predicted&gold); fp+=len(predicted-gold); fn+=len(gold-predicted)
 p=tp/(tp+fp) if tp+fp else 0; r=tp/(tp+fn) if tp+fn else 0; f=2*p*r/(p+r) if p+r else 0
 print(json.dumps({'pipeline':pipeline,'cases':len(CASES),'unit':'наличие типа факта в документе','tp':tp,'fp':fp,'fn':fn,'precision':p,'recall':r,'f1':f},ensure_ascii=True))

