import unittest,uuid
from unittest.mock import patch
from datetime import date
from db import init,connect
from recommend import recommend,shopping,norm_name,convert
from nlp import extract,save_extraction
C_FACTS='[{"kind":"ингредиент","value":{"name":"овсянка","quantity":100,"unit":"г"},"fragment":"овсянка 100 г"},{"kind":"правило","value":{"если":"закипело","то":"варить 10 минут"},"fragment":"Если закипело, то варить 10 минут"}]'
C_FACTS2='[{"kind":"ингредиент","value":{"name":"овсянка","quantity":200,"unit":"г"},"fragment":"овсянка 200 г"}]'
class Tests(unittest.TestCase):
 @classmethod
 def setUpClass(cls): init()
 def test_scaling(self):
  r,_=recommend([1],'завтрак',4); k=next(x for x in r if x['name']=='Овсяная каша'); self.assertEqual(next(x for x in k['ingredients'] if x['product']=='овсянка')['need'],200)
 def test_cooperation(self):
  self.assertEqual(recommend([1,2],'обед',2)[0][0]['status'],'можно приготовить'); self.assertEqual(recommend([1],'обед',2)[0][0]['status'],'не хватает продуктов')
 def test_equipment_expiry(self):
  r,w=recommend([2,3],'вечеринка',2,today=date(2026,1,1)); self.assertTrue(any('просрочен' in x for x in w)); self.assertTrue(any(x['missing'] for x in r[0]['ingredients'])); self.assertIn('принадлежностей',recommend([1,2],'вечеринка',2)[0][0]['status'])
 def test_normalize(self):
  self.assertEqual(norm_name('Томаты'),'помидор'); self.assertEqual(convert(1,'кг'),(1000,'г')); self.assertRaises(ValueError,convert,1,'стакан')
 def test_invalid(self):
  for ids,n in [([],2),([999],2),([1],0),([1],-1),([1,1],1)]: self.assertRaises(ValueError,recommend,ids,'обед',n)
 def test_shopping(self):
  items=shopping([1,2],'завтрак',2,[1,3]); self.assertEqual(next(x for x in items if x['product']=='сыр')['quantity'],50)
 def test_nlp(self):
  a,_=extract('Название: Каша\n2 порции\nовсянка 100 г\nЕсли закипело, то варите 10 минут'); self.assertTrue(any(x['kind']=='правило' for x in a)); self.assertTrue(any(x['kind']=='ингредиент' for x in a))
 def test_conflict(self):
  name=str(uuid.uuid4()); save_extraction('one','овсянка 100 г',name,'A'); eid=save_extraction('two','овсянка 200 г',name,'B')
  with connect() as c: self.assertGreater(c.execute('SELECT count(*) FROM conflicts WHERE fact_id IN (SELECT id FROM facts WHERE extraction_id=?)',(eid,)).fetchone()[0],0)
 def test_neural_c(self):
  with patch('neural.chat',return_value=(C_FACTS,'test-model')): eid=save_extraction('n1','овсянка 100 г\nЕсли закипело, то варить 10 минут',str(uuid.uuid4()),'C')
  with connect() as c:
   rows=c.execute('SELECT kind,value FROM facts WHERE extraction_id=? ORDER BY id',(eid,)).fetchall(); m=c.execute('SELECT model FROM extractions WHERE id=?',(eid,)).fetchone()
  self.assertEqual([x['kind'] for x in rows],['ингредиент','правило']); self.assertEqual(m['model'],'test-model')
  with patch('neural.chat',return_value=('мусор без json','test-model')): self.assertRaises(RuntimeError,save_extraction,'n2','текст',str(uuid.uuid4()),'C')
 def test_neural_conflict(self):
  name=str(uuid.uuid4())
  with patch('neural.chat',return_value=(C_FACTS,'test-model')): save_extraction('a','овсянка 100 г',name,'C')
  with patch('neural.chat',return_value=(C_FACTS2,'test-model')): eid=save_extraction('b','овсянка 200 г',name,'C')
  with connect() as c: self.assertGreater(c.execute('SELECT count(*) FROM conflicts WHERE fact_id IN (SELECT id FROM facts WHERE extraction_id=?)',(eid,)).fetchone()[0],0)
if __name__=='__main__': unittest.main()
