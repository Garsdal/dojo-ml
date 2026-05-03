import json, sys, traceback
sys.path.insert(0, '/Users/marcusgarsdal/Personal/Dojo/housing')
sys.path.insert(0, '.dojo/domains/01KQQ689CS7HZWSVYAJ70ZG176/tools')

try:
    from __dojo_train_1 import train
    from evaluate import evaluate
    metrics = evaluate(train())
    print('__DOJO_METRICS__:' + json.dumps(metrics))
except Exception as e:
    print('__DOJO_ERROR__:' + json.dumps({
        "type": type(e).__name__,
        "message": str(e),
        "traceback": traceback.format_exc(),
    }))
    sys.exit(1)
