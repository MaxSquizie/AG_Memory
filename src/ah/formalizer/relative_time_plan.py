"""Emit SOM nominal event anchors and explicit relative-time G roots in T5."""
from .canonical_ledger import digest


def emit_relative_time(state,frame,target,target_content_key,fragment,tag,emit,support):
    for row in frame.semantic.get('relative_temporal',()):
        anchor=row['anchor_ref']
        tid='T:open:event-anchor:'+digest([state.source_uid,anchor])
        emit('ENSURE_TEMPLATE',{'uid':tid,'predicate_form':row['anchor_lemma'],'roles':[],
            'semantic_status':'UNLINKED','source_ref':anchor,'source_tag':tag},fragment)
        content={'predicate':tid,'actants':{}}; ck=digest(content)
        nid='N:event-anchor:'+digest([state.source_uid,anchor])
        emit('ENSURE_NODE',{'uid':nid,'template_ref':tid,'actants':{},
            'semantic_status':'UNLINKED','temporal_mode':'EVENT',
            'identity_key':[ck,state.source_uid,anchor],'content_key':ck,
            'polarity':True,'proposition':content,'source_tag':tag,'source_ref':anchor},fragment)
        operands=[target,nid]; gid='G:'+digest([row['operator'],operands])
        key=digest([row['operator'],[target_content_key,ck]])
        emit('ENSURE_FUNCTION',{'uid':gid,'function_id':row['operator'],
            'operands':operands,'content_key':key,'polarity':True,
            'source_tag':tag},fragment)
        for position,child in enumerate(operands):
            link='usage:'+digest([child,gid,position,'OPERATOR'])
            emit('MATERIALIZE_USAGE_LINK',{'link_id':link,'node_ref':child,'parent_ref':gid,
                'position':position,'kind':'OPERATOR','operator':row['operator']},fragment)
        # The relation is directly expressed; the anchor is structural only.
        # No TimeAssertion exists without an absolute, licensed time region.
        support(gid,fragment,None)
        emit('DECLARE_FRAGMENT',{'fragment_id':fragment,'content_key':key,'polarity':True,
            'proposition':None,'region':None,'source_tag':tag,'node_ref':gid,
            'incompatibility_rules':[]},fragment)
