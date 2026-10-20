"""Offline binding of exported call records to their immutable provider receipts."""
import copy
from research.gemini_backend import GeminiBackend,GenerationSettings,InferenceError


def verify_call_record(call, receipt, item, execution):
    """Replay saved bytes in memory. This function cannot contact a provider."""
    def recorded_response(payload,settings):
        if receipt['status']=='ERROR':
            raise InferenceError('Recorded failure',code=receipt['code'],http_status=receipt['http_status'],
                retry_after_seconds=receipt.get('retry_after_seconds'),provider_diagnostics=receipt.get('provider_diagnostics'))
        if receipt['status']!='RESPONSE':
            raise ValueError('Unknown durable receipt state')
        return copy.deepcopy(receipt['response'])
    settings=GenerationSettings(**call['settings'])
    backend=GeminiBackend(settings,transport=recorded_response)
    try:
        backend.generate(call['system_prompt'],item,seed=call['seed'],stage=call['stage'],
            context=call['stage_context'],direct=call['stage'] in ('S0.direct','S2.adjudicate'))
    except InferenceError:
        pass  # A recorded failure is an outcome, never an excuse for a new send.
    if len(backend.records)!=1:
        raise ValueError('Call has no reconstructible provider observation')
    expected=backend.records[0]
    if receipt['status']=='ERROR' and receipt.get('response'):
        response=receipt['response'];usage=response.get('usageMetadata',{})
        expected['usage_metadata']=usage
        expected['model_version']=response.get('modelVersion');expected['response_id']=response.get('responseId')
        expected['tokens']={k:usage.get(v) for k,v in {
            'input':'promptTokenCount','output':'candidatesTokenCount','reasoning':'thoughtsTokenCount','total':'totalTokenCount'}.items()}
    expected.update(latency_seconds=receipt['provider_latency_seconds']+receipt['quota_wait_seconds'],
        provider_latency_seconds=receipt['provider_latency_seconds'],quota_wait_seconds=receipt['quota_wait_seconds'],
        attempt_id=receipt['attempt_id'],execution=execution)
    if call!=expected:
        raise ValueError('Call output, status, identity or usage differs from durable provider receipt')
    return True


def decoded_call_output(call):
    """Decode raw wire bytes while checking the persisted canonical observation."""
    from research.integrity import loads_json
    output = loads_json(call["output_text"])
    if call["settings"].get("profile") == "seed17_gemini35_wire_v1":
        if not call["stage"].endswith(".goal") and call["stage"] != "S1.context":
            from research.seed17_wire_codec import decode_task
            output = decode_task(output)
        if call.get("canonical_decoded_output") != output:
            raise ValueError("Canonical output differs from losslessly decoded provider bytes")
    return output
