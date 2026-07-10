import json, statistics as st
S='/private/tmp/claude-501/-Users-sgonzalez/4f584d6e-5c8f-4a76-8bd9-6dcf248c8bf8/scratchpad'
tr=json.load(open(S+'/data/trades.json'))
if isinstance(tr,dict): tr=tr.get('trades',tr)
rev=[x for x in tr if x.get('eng')=='reversal' or x.get('engine')=='reversal']
print('reversal trades:',len(rev))
if rev: print('sample keys:',sorted(rev[0].keys())); print(rev[0])
cur=[x for x in rev if 'prereset' not in str(x.get('src',''))]
print('current-src counts:',{})
import collections
print(collections.Counter(str(x.get('src')) for x in rev))
