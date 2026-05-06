import json

from django.core.serializers.json import DjangoJSONEncoder


def make_json_safe(value):
    return json.loads(json.dumps(value, cls=DjangoJSONEncoder))
