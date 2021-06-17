import json
import os
from pathlib import Path
import re
import sys

from metomi.rose.config import ConfigLoader, ConfigNode


# DATA_FILE = Path('../test-app/src/data.js').resolve()
# DATA_FILE = Path('../vue-form-json-schema-test-app/src/data.js').resolve()
DATA_PATH = Path('../react-app/src/').resolve()


def load_rose_schema(files):
    return ConfigLoader().load(files[0])


def rose_config_name_from_meta_entry(name):
    return '[{0}]{1}'.format(*name.split('='))


TYPE_MAP = {
    'boolean': 'boolean',
    'integer': 'integer',
    'raw': 'string',
    'str_multi': 'string',
    'string': 'string',
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


def rose_meta_split(string):
    """
        >>> rose_meta_split('foo')
        ['foo']
        >>> rose_meta_split('env=foo')
        ['env', 'foo']
        >>> rose_meta_split('namelist:foo=bar')
        ['namelist', 'foo', 'bar']
    """
    return re.split('[:=]', string)


def parse_range(range_string):
    """
    Examples:
        >>> parse_range('1')
        (1, 1)
        >>> parse_range('1:3')
        (1, 3)
        >>> parse_range(':')
        (None, None)
        >>> parse_range('1 3 5')
        (1, 5)
        >>> parse_range('1 2:6 5')
        (1, 6)
    """
    ret = []
    for string in range_string.split():
        parts = [
            int(x) if x else None
            for x in string.split(':')
        ]
        if len(parts) == 1:
            min_ = max_ = parts[0]
        elif len(parts) == 2:
            min_ = parts[0] or None
            max_ = parts[1] or None
        ret.append((min_, max_))
    # TODO: test for non-inclusive range and turn this into a server side rule
    return (
        min(x[0] for x in ret),
        max(x[1] for x in ret),
    )


def property_name(*keys):
    """
        >>> property_name('foo')
        '#/properties/foo'
        >>> property_name('foo', 'bar', 'baz')
        '#/properties/foo/properties/bar/properties/baz'
    """
    return f'#/properties/{"/properties/".join(keys)}'


def construct_node(keys, node):
    schema_node = {}
    form_node = {'options': {}}
    typ = None
    make_array = False
    required = False
    for key, sub_node in node.value.items():
        value = sub_node.value
        if key == 'type':
            if ',' in value:
                typ = 'array'
                schema_node.update({
                    'type': typ,  # not needed
                    'items': [
                        {
                            'type': type_.strip()
                        }
                        for type_ in value.split(',')
                    ],
                    'additionalItems': False,
                    'minItems': len(value.split(',')),
                    'maxItems': len(value.split(','))
                })
            else:
                typ = TYPE_MAP[value]
                if value == 'str_multi':
                    form_node['options']['multi'] = True
        elif key == 'length':
            make_array = True
        elif key == 'values':
            typ = 'string'
            schema_node['enum'] = value.split()
        elif key == 'range':
            schema_node['minimum'], schema_node['maximum'] = parse_range(value)
        elif key == 'pattern':
            schema_node['pattern'] = value
        elif key == 'compulsory':
            required = True
    schema_node['type'] = typ
    if make_array:
        schema_node = {
            'type': 'array',
            'items': {
                **schema_node
            }
        }

    form_node = {
        'type': 'Control',
        'scope': property_name(*keys),
        **form_node
    }

    return (
        schema_node,
        form_node,
        required
    )


def expand_form_schema(form_node):
    if 'index' not in form_node:
        return form_node
    for key, node in form_node['index'].items():
        form_node['elements'].append({
            'type': 'Label',
            'text': f'{key}'
        })
        form_node['elements'].append(node)
        del form_node['index']
        expand_form_schema(node)

    return form_node


def convert_schema(meta_node):
    json_schema = {
        'type': 'object',
        'properties': {},
        'reqired': []
    }
    form_schema = {
        'type': 'VerticalLayout',
        'elements': [],
        'index': {}
    }

    for name, node in meta_node.value.items():
        keys = rose_meta_split(name)

        # construct tree
        parent_schema_node = json_schema
        parent_form_node = form_schema
        for key in keys[:-1]:
            parent_schema_node['properties'].setdefault(
                key,
                {
                    'type': 'object',
                    'properties': {}
                }
            )
            parent_schema_node = parent_schema_node['properties'][key]
            parent_form_node['index'].setdefault(
                key,
                {
                    'type': 'VerticalLayout',
                    'elements': []
                }
            )
            parent_form_node = parent_form_node['index'][key]

        # construct node
        schema_node, form_node, required = construct_node(keys, node)
        # if required:
        #     json_schema['required'].append(keys)

        # append node
        parent_schema_node['properties'][keys[-1]] = schema_node
        parent_form_node['elements'].append(form_node)

    # expand index entries
    expand_form_schema(form_schema)

    return json_schema, form_schema


def handle_latent(config, meta_config, form_config, show_latent=False):
    # TODO
    # second thought, easiest solution is just to do nothing and sort this
    # out in the ui somehow since we want to be able to change the appearance
    # of the latent settings/sections/whatevers in the UI which makes it a
    # UI problem NOT something that could be farmed out to the server
    pass


def dump_test_data(json_schema, form_schema, initial_data):
    # with open(DATA_FILE, 'w+') as data_file:
    #     data_file.write(
    #         f'export const jsonSchema = {json.dumps(json_schema, indent=2)}\n'
    #         f'export const formSchema = {json.dumps(form_schema, indent=2)}'
    #     )
    with open(DATA_PATH / 'schema.json', 'w+') as json_schema_file:
        json.dump(json_schema, json_schema_file, indent=2)
    with open(DATA_PATH / 'uischema.json', 'w+') as form_schema_file:
        json.dump(form_schema, form_schema_file, indent=2)
    with open(DATA_PATH / 'initialData.json', 'w+') as data_file:
        json.dump(initial_data, data_file, indent=2)


def rose_config_to_json(config):
    data = {}
    for keys, config_node in config.walk():
        if isinstance(config_node.value, dict):
            continue
        ptr = data
        for key in keys[:-1]:
            ptr.setdefault(key, {})
            ptr = ptr[key]
        ptr[keys[-1]] = config_node.value
    return data


def json_to_rose_config(data):
    pass


def main():
    config_dir = Path(sys.argv[1])
    config = ConfigLoader().load(str(config_dir / 'rose-app.conf'))
    meta_config = ConfigLoader().load(str(config_dir / 'meta/rose-meta.conf'))

    json_schema, form_schema = convert_schema(meta_config)
    handle_latent(config, meta_config, form_schema, show_latent=False)

    initial_data = rose_config_to_json(config)

    print('# json schema')
    print(json.dumps(json_schema, indent=2))
    print('# ui schema')
    print(json.dumps(form_schema, indent=2))
    print('# initial data')
    print(json.dumps(initial_data, indent=2))

    # return

    dump_test_data(json_schema, form_schema, initial_data)


if __name__ == '__main__':
    main()
