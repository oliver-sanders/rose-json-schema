import json
from pathlib import Path
import sys

from metomi.rose.config import ConfigLoader


# DATA_FILE = Path('../test-app/src/data.js').resolve()
# DATA_FILE = Path('../vue-form-json-schema-test-app/src/data.js').resolve()
DATA_PATH = Path('../react-app/src/').resolve()


def load_rose_schema(files):
    return ConfigLoader().load(files[0])


def rose_config_name_from_meta_entry(name):
    return '[{0}]{1}'.format(*name.split('='))


TYPE_MAP = {
    'string': 'string',
    'str_multi': 'string',
    'integer': 'integer',
    'boolean': 'boolean'
}


def blank_schema(meta_node):
    return {
        # '$schema': 'https://json-schema.org/draft/2020-12/schema',
        # '$id': 'https://cylc.org/my-schema',
        # 'title': 'demo',
        # 'type': 'object',
        'properties': {},
        'required': []
    }


def convert_schema(meta_node):
    json_schema = blank_schema(meta_node)
    form_schema = {
        'type': 'VerticalLayout',
        'elements': []
    }
    for name, node in meta_node.value.items():
        name = name.split('=')[1]
        schema_node = {}
        form_node = {'options': {}}
        typ = None
        is_array = False
        values = None
        for key, sub_node in node.value.items():
            if key == 'type':
                typ = TYPE_MAP[sub_node.value]
                if sub_node.value == 'str_multi':
                    form_node['options']['multi'] = True
            if key == 'length':
                is_array = True
            if key == 'values':
                typ = 'string'
                schema_node['enum'] = sub_node.value.split()
        schema_node['type'] = typ
        if is_array:
            schema_node = {
                'typ': 'array',
                'items': {
                    **schema_node
                }
            }
            form_node['options'].update({
                'detail': 'DEFAULT',
                'showSortButtons': True,
            })
        json_schema['properties'][name] = schema_node
        form_schema['elements'].append({
            'type': 'Control',
            'scope': f'#/properties/{name}',
            **form_node
        })
    return json_schema, form_schema


def dump_test_data(json_schema, form_schema):
    # with open(DATA_FILE, 'w+') as data_file:
    #     data_file.write(
    #         f'export const jsonSchema = {json.dumps(json_schema, indent=2)}\n'
    #         f'export const formSchema = {json.dumps(form_schema, indent=2)}'
    #     )
    with open(DATA_PATH / 'schema.json', 'w+') as json_schema_file:
        json.dump(json_schema, json_schema_file)
    with open(DATA_PATH / 'uischema.json', 'w+') as form_schema_file:
        json.dump(form_schema, form_schema_file)


def main():
    rose_schema = load_rose_schema(sys.argv[1:])
    json_schema, form_schema = convert_schema(rose_schema)
    print(json.dumps(json_schema, indent=2))
    print(json.dumps(form_schema, indent=2))
    dump_test_data(json_schema, form_schema)


if __name__ == '__main__':
    main()
