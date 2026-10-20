"""Evaluator-only reconstruction of already released, exactly approved replies."""


def restore_released(oracle, queries, state_attribute="active"):
    if not isinstance(queries,list) or not queries:
        raise ValueError("Nonempty released-prefix reconstruction required")
    old = getattr(oracle,state_attribute)
    setattr(oracle,state_attribute,{})
    try:
        for entry in queries:
            if not isinstance(entry,dict) or set(entry) != {"sequence","record_id","branch_id","question","turn","answer"}:
                raise ValueError("Invalid released oracle prefix")
            query = {k:v for k,v in entry.items() if k != "answer"}
            if oracle.answer(**query) != entry["answer"]:
                raise ValueError("Stored reply is not the approved matching answer")
        rebuilt = getattr(oracle,state_attribute)
    except BaseException:
        setattr(oracle,state_attribute,old)
        raise
    setattr(oracle,state_attribute,{**old,**rebuilt})
    return True
