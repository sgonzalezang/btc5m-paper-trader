import json, statistics as st
S='/private/tmp/claude-501/-Users-sgonzalez/4f584d6e-5c8f-4a76-8bd9-6dcf248c8bf8/scratchpad'
tr=json.load(open(S+'/data/trades.json'))
if isinstance(tr,dict): tr=tr.get('trades',tr)
rev=[x for x in tr if x.get('eng')=='reversal' and x.get('status')=='settled']
print('settled reversal trades:',len(rev),'pnl total %.2f'%sum(x['pnl'] for x in rev))
ent=[x['entry'] for x in rev]
print('entry: min %.3f p25 %.3f med %.3f p75 %.3f max %.3f'%(min(ent),sorted(ent)[len(ent)//4],st.median(ent),sorted(ent)[3*len(ent)//4],max(ent)))
wins=[x for x in rev if x['result']=='win']
print('win rate %.4f (%d/%d)'%(len(wins)/len(rev),len(wins),len(rev)))
# PnL decomposition by entry bucket
for lo,hi in [(0,0.45),(0.45,0.505),(0.505,0.53),(0.53,1.0)]:
    b=[x for x in rev if lo<=x['entry']<hi]
    if b: print('entry [%.2f,%.2f): n=%2d win=%.3f pnl=%+8.2f avg=%+.2f'%(lo,hi,len(b),sum(1 for x in b if x['result']=='win')/len(b),sum(x['pnl'] for x in b),sum(x['pnl'] for x in b)/len(b)))
# spec-conformant subset: entry <= 0.53
spec=[x for x in rev if x['entry']<=0.53]
print('spec subset (entry<=0.53): n=%d win=%.4f pnl=%+.2f (%.2f/trade)'%(len(spec),sum(1 for x in spec if x['result']=='win')/len(spec),sum(x['pnl'] for x in spec),sum(x['pnl'] for x in spec)/len(spec)))
near50=[x for x in rev if 0.49<=x['entry']<=0.53]
print('entry in [0.49,0.53]: n=%d win=%.4f pnl/trade %+.2f'%(len(near50),sum(1 for x in near50 if x['result']=='win')/len(near50),sum(x['pnl'] for x in near50)/len(near50)))
# what fraction of live pnl comes from deep-discount entries (<0.49)?
deep=[x for x in rev if x['entry']<0.49]
print('deep discount (<0.49): n=%d win=%.4f pnl=%+.2f'%(len(deep),sum(1 for x in deep if x['result']=='win')/len(deep),sum(x['pnl'] for x in deep)))
# entrySec and fillFrac
print('entrySec med',st.median(x['entrySec'] for x in rev),'fillFrac',set(round(x['fillFrac'],2) for x in rev))
# time span of live trades
print('span days %.2f'%((max(x['t0'] for x in rev)-min(x['t0'] for x in rev))/86400))
