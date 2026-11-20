"""Connect the native cache selection point to the team's agreement-4/5 modules."""
from aiida import orm
from ai4s_query.candidates import build_candidate
from ai4s_engine.candidate_selection import reject_identity_unresolved_candidates
from ai4s_workflows.cost_decision import configured_cost_decision_function
from ai4s_workflows.decision import DecisionError, make_decision_record, save_decision_record


def select_cache(node, native_candidates):
    context = node.base.extras.get('ai4s_context')
    candidates, source_by_output = [], {}
    sources = {source.uuid: source for source in native_candidates}
    unresolved = node.base.attributes.get('ai4s_identity_unresolved', None)
    if not unresolved:
        fingerprint = node.base.caching._compute_hash()
        for (source,) in orm.QueryBuilder().append(orm.CalcJobNode, filters={'extras._aiida_hash': fingerprint}).all():
            sources.setdefault(source.uuid, source)
    for source in sources.values():
        candidate = build_candidate(source, context['profile'], {'num_sequences': context['num_sequences']})
        # Preserve the producer's identity after archive transfer or a different requester.
        producer = source.base.extras.get('ai4s_requester', {}) or source.base.extras.get('ai4s_context', {}).get('requester', {})
        candidate['member'] = producer.get('display_name', candidate['member'])
        candidate['fingerprint'] = source.base.caching.get_hash()
        if not source.base.caching.is_valid_cache:
            candidate['qualified'] = False
            candidate['reason'] = candidate['reason'] or 'format_error: native cache validity rejected'
        candidates.append(candidate)
        source_by_output[candidate['uuid']] = source
    known = {(candidate['uuid'], candidate['fingerprint']) for candidate in candidates}
    for candidate in context.get('shared_candidates', []):
        if (candidate['uuid'], candidate['fingerprint']) not in known:
            # A listed foreign result is not proof that native caching can use
            # it. Never emit R01 unless there is an actual native cache source.
            candidate = dict(candidate)
            if candidate['qualified']:
                candidate.update(qualified=False, reason='format_error: result is not indexed as a native cache source')
            candidates.append(candidate)
    shared = {(item['uuid'], item['fingerprint']): item for item in context.get('shared_candidates', [])}
    candidates = [shared.get((item['uuid'], item['fingerprint']), item)
                  if item['qualified'] else item for item in candidates]
    if unresolved:
        reject_identity_unresolved_candidates(candidates, unresolved)
    cost_decision = None
    if context['reuse_policy'] == 'allow_reuse':
        cost_decision = configured_cost_decision_function()
        if context.get('cost_decision_required') is True and cost_decision is None:
            raise DecisionError(
                'cost decision was required when the request was submitted, '
                'but the daemon cannot load an enabled cost policy'
            )
    record = make_decision_record(
        request_id=context['request_id'], process_uuid=node.uuid,
        reuse_policy=context['reuse_policy'], candidates=candidates,
        original_seed=context['original_seed'], decision_function=cost_decision,
        seed_factory=lambda _: context['effective_seed'])
    if unresolved:
        record['reason']['reason_text'] += '; 模型身份无法确定，禁止缓存：' + unresolved
    save_decision_record(node, record)
    selected = record['final_decision']['selected_candidate_uuid']
    return source_by_output.get(selected)
