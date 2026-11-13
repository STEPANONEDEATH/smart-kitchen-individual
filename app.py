import json
import streamlit as st
from db import init,connect
from recommend import recommend,shopping,convert,norm_name
from nlp import save_extraction
init(); st.set_page_config(page_title='Умная кухня',layout='wide'); st.title('Умная кухня')
with connect() as c:
    fridges=c.execute('SELECT f.id,f.name,o.name owner FROM fridges f JOIN owners o ON o.id=f.owner_id').fetchall()
    products=c.execute('SELECT * FROM products').fetchall(); equipment=c.execute('SELECT * FROM equipment').fetchall()
tab1,tab2,tab3,tab4=st.tabs(['Подбор и покупки','Запасы','Рецепты','Анализ текста'])
with tab1:
    names={f"{x['name']} — {x['owner']}":x['id'] for x in fridges}
    selected=st.multiselect('Холодильники и владельцы',list(names),default=list(names)[:1]); event=st.selectbox('Событие',['завтрак','обед','ужин','вечеринка']); people=st.number_input('Число человек',min_value=1,value=2); servings=st.number_input('Число порций',min_value=1,value=int(people)); ids=[names[x] for x in selected]
    try:
        results,warnings=recommend(ids,event,int(servings))
        for w in warnings: st.warning(w)
        for r in results:
            with st.expander(r['name']+' — '+r['status'],expanded=True):
                st.table(r['ingredients']); st.write('Не хватает принадлежностей:',', '.join(r['equipment_missing']) or 'нет')
        choices={r['name']:r['id'] for r in results}; chosen=st.multiselect('Блюда для общего меню',list(choices))
        if chosen:
            items=shopping(ids,event,int(servings),[choices[x] for x in chosen]); st.write('Черновик списка покупок:',items or 'всё есть')
            if st.button('Сохранить список покупок'):
                with connect() as c:
                    lid=c.execute('INSERT INTO shopping_lists(event,servings,fridge_ids) VALUES (?,?,?)',(event,int(servings),json.dumps(ids))).lastrowid
                    c.executemany('INSERT INTO shopping_items VALUES (?,?,?,?)',[(lid,x['product'],x['quantity'],x['unit']) for x in items])
                st.success(f'Список № {lid} сохранён. Реальный заказ не отправлен.')
    except ValueError as e: st.info(str(e))
with tab2:
    with connect() as c:
        st.dataframe([dict(r) for r in c.execute('SELECT f.name холодильник,o.name владелец,p.name продукт,s.quantity количество,s.unit единица,s.expires годен_до FROM stock s JOIN fridges f ON f.id=s.fridge_id JOIN owners o ON o.id=f.owner_id JOIN products p ON p.id=s.product_id')],width='stretch')
    st.caption('Пустой срок означает, что его необходимо проверить. Отдельные партии одного продукта суммируются.')
with tab3:
    with connect() as c:
        for r in c.execute('SELECT * FROM recipes').fetchall():
            with st.expander(f"{r['name']} — {r['servings']} порц."):
                st.write('События:',', '.join(x[0] for x in c.execute('SELECT event FROM recipe_events WHERE recipe_id=?',(r['id'],))))
                st.table([dict(x) for x in c.execute('SELECT p.name продукт,i.quantity количество,i.unit единица FROM ingredients i JOIN products p ON p.id=i.product_id WHERE recipe_id=?',(r['id'],))]); st.write([x[0] for x in c.execute('SELECT text FROM steps WHERE recipe_id=? ORDER BY position',(r['id'],))])
    st.subheader('Добавить рецепт')
    with st.form('recipe'):
        name=st.text_input('Название'); base=st.number_input('Базовое число порций',min_value=1,value=2); events=st.multiselect('События',['завтрак','обед','ужин','вечеринка']); raw=st.text_area('Ингредиенты: по строке «продукт; количество; единица»'); eq=st.multiselect('Принадлежности',[x['name'] for x in equipment]); steps=st.text_area('Этапы: по одному на строку'); submit=st.form_submit_button('Добавить')
        if submit:
            try:
                if not name.strip() or not events or not raw.strip(): raise ValueError('Укажите название, событие и ингредиенты')
                parsed=[]; seen=set()
                for line in raw.splitlines():
                    p,q,u=[x.strip() for x in line.split(';')]; p=norm_name(p); q,u=convert(float(q.replace(',','.')),u)
                    if q<=0 or p in seen: raise ValueError('Количество должно быть положительным; продукт не должен повторяться')
                    seen.add(p); parsed.append((p,q,u))
                with connect() as c:
                    rid=c.execute('INSERT INTO recipes(name,servings) VALUES (?,?)',(name.strip(),int(base))).lastrowid
                    c.executemany('INSERT INTO recipe_events VALUES (?,?)',[(rid,e) for e in events])
                    for p,q,u in parsed:
                        c.execute('INSERT OR IGNORE INTO products(name,unit) VALUES (?,?)',(p,u)); row=c.execute('SELECT id,unit FROM products WHERE name=?',(p,)).fetchone()
                        if row['unit']!=u: raise ValueError('Несовместимая единица для '+p)
                        c.execute('INSERT INTO ingredients VALUES (?,?,?,?)',(rid,row['id'],q,u))
                    for e in eq: c.execute('INSERT INTO recipe_equipment SELECT ?,id FROM equipment WHERE name=?',(rid,e))
                    c.executemany('INSERT INTO steps(recipe_id,position,text) VALUES (?,?,?)',[(rid,i,x) for i,x in enumerate(steps.splitlines(),1) if x.strip()])
                st.success('Рецепт добавлен'); st.rerun()
            except Exception as e: st.error('Рецепт не сохранён: '+str(e))
with tab4:
    st.caption('Все результаты — кандидаты. A/B — эвристическое извлечение, C — извлечение правил и сущностей LLM (конечная точка задаётся переменными KITCHEN_LLM_*); решение за человеком.')
    with st.form('nlp'):
        uploaded=st.file_uploader('Загрузить текст UTF-8',type=['txt']); source=st.text_input('Название источника',value='Учебный источник'); recipe=st.text_input('Общее название рецепта для сравнения',value='Каша'); text=st.text_area('Текст рецепта',height=200,value='Название: Каша\n2 порции\nовсянка 100 г\nмолоко 300 мл\nЕсли смесь закипела, то варите 10 минут'); order=st.selectbox('Конвейер',['A','B','C'],format_func=lambda x:{'A':'A — эвристики: сущности, затем связи','B':'B — эвристики: связи, затем сущности','C':'C — нейросеть (LLM, KITCHEN_LLM_BASE_URL)'}[x]); neural=st.checkbox('Классификатор строк (XNLI, только для A/B)'); run=st.form_submit_button('Извлечь кандидаты')
        if run:
            try:
                if not source.strip() or not recipe.strip(): raise ValueError('Укажите источник и рецепт')
                eid=save_extraction(source,uploaded.getvalue().decode('utf-8-sig') if uploaded else text,recipe,order,neural); st.success(f'Сохранён анализ № {eid}')
            except Exception as e: st.error(str(e))
    with connect() as c:
        extracted=c.execute('SELECT e.id,s.name,s.recipe_name,e.pipeline,e.model FROM extractions e JOIN sources s ON s.id=e.source_id ORDER BY e.id DESC').fetchall()
        if extracted:
            options={f"№{x['id']} — {x['recipe_name']} / {x['name']} / {x['pipeline']} / {x['model']}":x['id'] for x in extracted}; chosen_id=options[st.selectbox('Анализ',list(options))]
            facts=c.execute('SELECT * FROM facts WHERE extraction_id=? ORDER BY id',(chosen_id,)).fetchall()
            for f in facts:
                st.write(f"#{f['id']} **{f['kind']}**: {f['value']} | фрагмент: {f['fragment']} | уверенность: {f['confidence']} | {f['status']}")
                conflicts=c.execute('SELECT c.explanation,f.value,s.name FROM conflicts c JOIN facts f ON f.id=c.other_fact_id JOIN extractions e ON e.id=f.extraction_id JOIN sources s ON s.id=e.source_id WHERE c.fact_id=?',(f['id'],)).fetchall()
                for conflict in conflicts: st.warning(f"Возможный конфликт: {conflict['explanation']} Другое значение: {conflict['value']} ({conflict['name']})")
                a,b=st.columns(2)
                if a.button('Подтвердить',key='yes'+str(f['id'])):
                    c.execute("UPDATE facts SET status='подтверждено' WHERE id=?",(f['id'],)); c.commit(); st.rerun()
                if b.button('Отклонить',key='no'+str(f['id'])):
                    c.execute("UPDATE facts SET status='отклонено' WHERE id=?",(f['id'],)); c.commit(); st.rerun()

