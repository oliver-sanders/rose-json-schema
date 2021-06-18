import json
from pathlib import Path
import re
import sys

from metomi.rose.config import ConfigLoader


# DATA_FILE = Path('../test-app/src/data.js').resolve()
# DATA_FILE = Path('../vue-form-json-schema-test-app/src/data.js').resolve()
DATA_PATH = Path('../react-app/src/').resolve()


def to_bool(string):
    """
        >>> to_bool('true')
        True
        >>> to_bool('.true.')
        True
        >>> to_bool('True')
        True

        >>> to_bool('false')
        False
        >>> to_bool('.false.')
        False
        >>> to_bool('False')
        False
    """
    if string.replace('.', '').lower() == 'true':
        return True
    if string.replace('.', '').lower() == 'false':
        return False
    raise ValueError(string)


TYPE_MAP = {
    'boolean': 'boolean',
    'integer': 'integer',
    'raw': 'string',
    'str_multi': 'string',
    'string': 'string',
}

CONVERTERS = {
    'boolean': to_bool,
    'integer': int,
    'string': str,
}


def get_converter(typ, length):
    """
        >>> get_converter('boolean', None)('true')
        True
        >>> get_converter('boolean', '1')('true')
        [True]
        >>> get_converter('boolean', ':')('true false true')
        [True, False, True]
        >>> get_converter('boolean,integer,string', None)('true 42 str')
        [True, 42, 'str']


    """
    is_compound = ',' in typ
    if is_compound and length:
        raise NotImplementedError()
    if is_compound:
        type_list = [
            type_item.strip()
            for type_item in typ.split(',')
        ]
        return convert_compound(type_list)
    if length:
        # allows any number of elements of type "typ"
        return convert_compound(typ)
    else:
        # allows a single element of type "typ"
        return CONVERTERS[TYPE_MAP[typ.strip()]]


def convert_compound(type_list):
    """
        >>> convert_compound(['string', 'integer'])('answer 42')
        ['answer', 42]

        >>> convert_compound('boolean')('true false true')
        [True, False, True]
    """

    def _convert(value):
        nonlocal type_list
        value_list = [
            val.strip()
            for val in value.split(' ')
        ]
        ret = []
        if isinstance(type_list, str):
            type_list = [type_list] * len(value_list)
        for val, typ in zip(value_list, type_list):
            converter = CONVERTERS[TYPE_MAP[typ]]
            ret.append(
                converter(val)
            )
        return ret
    return _convert


def meta_entry_from_rose_config_name(keys):
    """
        >>> meta_entry_from_rose_config_name(('env',))
        'env'
        >>> meta_entry_from_rose_config_name(('env', 'foo'))
        'env=foo'
        >>> meta_entry_from_rose_config_name(('namelist', 'foo', 'bar'))
        'namelist:foo=bar'
    """
    if len(keys) == 1:
        return keys[0]
    elif len(keys) == 2:
        # TODO: this isn't necessarily true is it?
        return f'{keys[0]}={keys[1]}'
    elif len(keys) == 3:
        return f'{keys[0]}:{keys[1]}={keys[2]}'


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


def parse_length(length_string):
    """
        >>> parse_length('3')
        (3, 3)
        >>> parse_length(':')
        (None, None)
    """
    length_string = length_string.strip()
    if length_string == ':':
        return (None, None)
    length = int(length_string)
    return (length, length)


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
                    # TODO: can this be combined with length?
                    'minItems': len(value.split(',')),
                    'maxItems': len(value.split(','))
                })
            else:
                typ = TYPE_MAP[value]
                if value == 'str_multi':
                    form_node['options']['multi'] = True
        elif key == 'length':
            make_array = parse_length(value)
        elif key == 'values':
            typ = 'string'
            schema_node['enum'] = [
                val.strip()
                for val in value.split(',')
            ]
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
        if all(make_array):
            # TODO: this better
            schema_node.update({
                # TODO: lookup this
                'additionalItems': False,
                'minItems': make_array[0],
                'maxItems': make_array[1],
            })

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
    """
    Essentially a shortcut to avoid having to sort the metadata upfront.
    """
    if 'index' not in form_node:
        return form_node
    for _key, node in form_node['index'].items():
        form_node['elements'].append(node)
        expand_form_schema(node)
    del form_node['index']
    return form_node


def convert_schema(meta_node):
    json_schema = {
        'type': 'object',
        'properties': {},
    }
    form_schema = {
        'type': 'Categorization',
        'elements': [],
        'index': {}
    }

    for name, node in meta_node.value.items():
        keys = rose_meta_split(name)

        # construct tree
        parent_schema_node = json_schema
        parent_form_node = form_schema
        for level, key in enumerate(keys[:-1]):
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
                    'type': 'Category' if level == 0 else 'Group',
                    'label': key,
                    'elements': [],
                    'index': {}
                }
            )
            parent_form_node = parent_form_node['index'][key]

        # construct node
        schema_node, form_node, required = construct_node(keys, node)
        if required:
            parent_schema_node.setdefault('required', []).append(keys[-1])
            # json_schema['required'].append('/'.join(keys))

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


def resolve_type(config_node, meta_node):
    typ = meta_node.get('type')
    length = meta_node.get('length')
    if typ:
        typ = typ.value
    else:
        typ = 'string'
    if length:
        length = length.value
    value = config_node.value

    converter = get_converter(typ, length)
    return converter(value)


def rose_config_to_json(config, meta_config):
    data = {}
    for keys, config_node in config.walk():
        if isinstance(config_node.value, dict):
            # don't do anything for config sections
            continue

        # get rose metadata
        meta_key = meta_entry_from_rose_config_name(keys)
        meta_node = meta_config.get([meta_key]).value

        if ':' in keys[0]:
            # convert ['namelist:foo'] to ['namelist', 'foo']
            keys = keys[0].split(':') + keys[1:]

        # construct the tree
        ptr = data
        for key in keys[:-1]:
            ptr.setdefault(key, {})
            ptr = ptr[key]

        # add the config entry
        ptr[keys[-1]] = resolve_type(config_node, meta_node)

    return data


def json_to_rose_config(data):
    pass


def main():
    config_dir = Path(sys.argv[1])
    config = ConfigLoader().load(str(config_dir / 'rose-app.conf'))
    meta_config = ConfigLoader().load(str(config_dir / 'meta/rose-meta.conf'))

    json_schema, form_schema = convert_schema(meta_config)
    handle_latent(config, meta_config, form_schema, show_latent=False)

    initial_data = rose_config_to_json(config, meta_config)

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
