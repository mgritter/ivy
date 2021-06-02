#
# Copyright (c) Microsoft Corporation. All Rights Reserved.
#

# This script extracts some Ivy declarations from a Swagger
# specification in JSON format.
#
# Usage:
#
#     python extract.py file.json
#

import sys
import os
import json
import collections
import ivy.ivy_utils

def format_error(inpname,err):
    sys.stderr.write('bad format in {}: {}\n'.format(inpname,err))
    exit(1)

name_counter = 0

# Ivy reserved words

ivy_words = {
    'relation',
   'individual',
   'function',
   'axiom',
   'conjecture',
   'schema',
   'instantiate',
   'instance',
   'derived',
   'concept',
   'init',
   'action',
   'method',
   'state',
   'assume',
   'assert',
   'set',
   'null',
   'old',
   'from',
   'update',
   'params',
   'in',
   'match',
   'ensures',
   'requires',
   'modifies',
   'true',
   'false',
   'fresh',
   'module',
   'object',
   'class',
   'type',
   'if',
   'else',
   'local',
   'let',
   'call',
   'entry',
   'macro',
   'interpret',
   'forall',
   'exists',
   'returns',
   'mixin',
   'execute',
   'before',
   'after',
   'isolate',
   'with',
   'export',
   'delegate',
   'import',
   'using',
   'include',
   'progress',
   'rely',
   'mixord',
   'extract',
   'destructor',
   'some',
   'maximizing',
   'minimizing',
   'private',
   'implement',
   'property',
   'while',
   'invariant',
   'struct',
   'definition',
   'ghost',
   'alias',
   'trusted',
   'this',
   'var',
   'attribute',
   'variant',
   'of',
   'scenario',
   'proof',
   'named',
   'fresh',
   'temporal',
   'globally',
   'eventually',
   'decreases',
   'specification',
   'implementation',
   'ensure',
   'require',
   'around',
   'parameter',
   'apply',
   'theorem',
   'showgoals',
   'defergoal',
   'spoil',
   'explicit',
   'thunk',
    'isa',
   'autoinstance',
   'constructor',
}

# Headers taht seem to be missing from the C++ SDKOptions

missing_headers = set([
    "GetBucketNotification",
    "GetBucketLifecycle",
    "PutBucketLifecycle",
    "PutBucketNotification",
    ])

types_with_string_conv = [
    "RequestPayer",
    "ServerSideEncryption",
    "StorageClass",
    "RequestCharged",
    "ReplicationStatus",
    "ObjectLockMode",
    "ObjectLockLegalHoldStatus",
    "ObjectCannedACL",
]


# Convert swagger name to ivy name
#
# - Initial capitals prefixed with underscore
# - Non-alphanum characters converted to underscore
#

def iname(name):
    name = ''.join(('_' if not x.isalnum() else x) for x in name)
    if name[0].isupper():
        name = '_' + name
    if name in ivy_words:
        name = '_' + name
    if name == "boolean":
        return "bool"
    return name.replace('-','_')


def main():
    if len(sys.argv) != 2 or not sys.argv[1].endswith('.json'):
        sys.stderr.write('syntax: python extract.py <file>.json\n')
        exit(1)

    inpname = sys.argv[1]
    outname = iname(inpname[:-5])+'.ivy'

    try:
        with open(inpname) as inp:
            try:
                spec = json.load(inp,object_pairs_hook=collections.OrderedDict)
            except:
                format_error(inpname,'JSON error')
    except:
        sys.stderr.write('cannot open {} to read\n'.format(inpname))
        exit(1)

    try:
        out = open(outname,'w')
    except:
        sys.stderr.write('cannot open {} to write\n'.format(outname))
        exit(1)
        
    out.write('#lang ivy1.7\n')
    out.write('\n')
    out.write('# File generated from {}. Do not edit.\n'.format(inpname))
    out.write('\n')
    out.write('type unit\n')
    out.write('type string\n')
    out.write('type integer\n')
    out.write('type list\n')
    out.write('type timestamp\n')
    out.write('type long\n')
    out.write('include collections\n')
    out.write('include mymap\n')
    out.write('type byte\n')
    out.write('interpret byte->bv[8]\n')
    out.write('instance blob : vector(byte)\n')
    out.write('attribute libspec="aws-cpp-sdk-s3,aws-cpp-sdk-core,aws-crt-cpp,aws-c-common"')
    
    if not isinstance(spec,dict):
        format_error(inpname,'top-level not a dictionary')

    defs = spec["shapes"]

    def follow(ref):
        rf = ref
        if rf.startswith("#/"):
            rf = rf[2:].split('/')
            thing = spec
            for word in rf:
                if word in thing:
                    thing = thing[word]
                else:
                    format_error(inpname,'undefined ref: {}'.format(rf))
            return thing
        format_error(inpname,'undefined ref: {}'.format(rf))
       
    def ref_basename(rf):
        return iname(rf)
        # if rf.startswith('#/definitions/'):
        #     return iname(rf[len('#/definitions/'):])
        # else:
        #     format_error(inpname,'reference {} is not a definition'.format(path,opname,respname))
        
    def_refs = collections.defaultdict(list)

    for name,value in defs.iteritems():
        if "properties" in value:
            props = value["properties"]
            for df in props.values():
                if "$ref" in df:
                    def_refs[name].append(df["$ref"][len('#/definitions/'):])
    order = [(y,x) for x in def_refs.keys() for y in def_refs[x]]
    ordered_names = ivy.ivy_utils.topological_sort(defs.keys(),order)
    defs = collections.OrderedDict((x,defs[x]) for x in ordered_names)
                    
    def get_ref_or_type(prop,name,df):
        if not isinstance(df,dict):
            format_error(inpname,'member {} of entry {} not a dictionary'.format(prop,name))
        if "type" in df:
            ty = df["type"]
            if ty == "list":
                if "member" not in df:
                    format_error(inpname,'property {} of entry {} has no member field'.format(prop,name))
                items = df["member"]
                return "vector[{}]".format(get_ref_or_type(prop,name,items))
            elif ty == "map":
                if "key" not in df:
                    format_error(inpname,'property {} of entry {} has no key field'.format(prop,name))
                key = get_ref_or_type(prop,name,df["key"])
                if "value" not in df:
                    format_error(inpname,'property {} of entry {} has no value field'.format(prop,name))
                value = get_ref_or_type(prop,name,df["value"])
                return "unordered_map[{}][{}]".format(key,value)
            elif ty == "object":
                if "additionalProperties" not in df:
                    format_error(inpname,'property {} of entry {} has no additionalProperties field'.format(prop,name))
                add_props = df["additionalProperties"]
#                global name_counter
#                name = prop+'_sub_'+str(name_counter)
#                name_counter += 1
#                emit_type(name,add_props)
#                ty = name
                return get_ref_or_type(prop,name,add_props)
            return iname(ty)
        elif "shape" in df:
            rf = df["shape"]
            if rf not in defs:
                format_error(inpname,'member {} of entry {} has unknown type {}'.format(prop,name,rf))
            ty = defs[rf]
            if "type" in ty and ty["type"] != "structure" or "shape" in ty:
                return get_ref_or_type(prop,name,ty)
            return ref_basename(rf)
        else:
            format_error(inpname,'member {} of entry {} has no type field'.format(prop,name))
#        if isinstance(ty,dict):
#            name = prop+'_sub_'+str(idx)
#            emit_type(name,ty)
#            ty = name
    

    def to_aws(arg,df):
        ty = get_ref_or_type("","",df)
        if ty == "string":
            res = arg + ".c_str()"
            sh = df["shape"]
            if sh in types_with_string_conv:
                res = "Aws::S3::Model::{}Mapper::Get{}ForName(".format(sh,sh) + res + ")"
            return res
        if ty == "timestamp":
            return "Aws::Utils::DateTime((int64_t)" + arg + ")"
        elif ty == "blob":
            return 'blob_to_iostream({})'.format(arg)
        elif ty.startswith('unordered_map'):
            return 'map_to_aws({})'.format(arg)
        return arg

    def from_aws(lhs,arg,df):
        ty = get_ref_or_type("","",df)
        if ty == "string":
            sh = df["shape"]
            if sh in types_with_string_conv:
                arg = "Aws::S3::Model::{}Mapper::GetNameFor{}(".format(sh,sh) + arg + ")"
            arg = arg + ".c_str()"
        elif ty == "timestamp":
            arg = arg + ".Millis()"
        elif ty == "blob":
#            return '{}.insert({}.end(), std::istream_iterator<char>({}),std::istream_iterator<char>{{}}); for(int i = 0; i < {}.size(); i++) {}[i] &= 0xff;\n'.format(lhs,lhs,arg,lhs,lhs)
            return '{{ char c; while ({}.get(c)) {}.push_back(((int)c)&0xff);}}'.format(arg,lhs)
        elif ty.startswith('unordered_map') or ty.startswith('vector'):
#            return 'for (auto it = {}.begin(), en = {}.end(); it != en; ++it) {{ {}[it->first.c_str()] = it->second.c_str(); }} \n'.format(arg,arg,lhs)
            return 'for (auto it = {}.begin(), en = {}.end(); it != en; ++it) {{ {}.resize({}.size()+1); {}.back().first = it->first.c_str(); {}.back().second = it->second.c_str(); }} \n'.format(arg,arg,lhs,lhs,lhs,lhs)
        return lhs + ' = ' + arg + ';\n'

    sorted_defs = []
    stack = set()
    heap = set()

    def recur_defs(name):
        if name in heap:
            return
        if name in stack:
            format_error(inpname,'recursive defined: {}'.format(name))

        stack.add(name)
        if name in defs:
            value = defs[name]
            if "members" in value:
                for x,y in value["members"].iteritems():
                    if "shape" in y:
                        recur_defs(y["shape"])
            if "member" in value:
                y = value["member"]
                if "shape" in y:
                    recur_defs(y["shape"])
            stack.remove(name)
            heap.add(name)
            sorted_defs.append(name)
                
    for name,value in defs.iteritems():
        recur_defs(name)
        
    for name in sorted_defs:
        value = defs[name]
        if not isinstance(value,dict):
            format_error(inpname,'entry {} not a dictionary'.format(name))
        if "members" in value:
            items = []
            items.append('object {} = {{\n'.format(iname(name)))
            items.append('    type this = struct {{\n'.format(iname(name)))
            props = value["members"]
            required = value.get("required",None)
            num_props = len(props)
            if not isinstance(props,dict):
                format_error(inpname,'members of entry {} not a dictionary'.format(name))
            for idx,(prop,df) in enumerate(props.iteritems()):
                ty = get_ref_or_type(prop,name,df)
                if required is not None and prop not in required:
                    ty = "option[{}]".format(ty)
                comment = ' # ' + df["description"] if "description" in df else ''
                items.append('        {}_ : {}{} {}\n'.format(iname(prop),ty,',' if idx < num_props-1 else '',comment))
            out.write('\n')
            if "description" in value:
                out.write('# ' + value["description"] + '\n')
            out.write(''.join(items))
            out.write('    }\n')
            out.write('}\n')

    operations = spec["operations"]

    def operation_name(op):
        return iname(op["name"])
    
    def request_name(op):
        return "request"

    def response_name(op,ty):
        return "response_{}".format(ty)

    operation_count = 0
    for operation,op in operations.iteritems():
        operation_count = operation_count + 1
        if not isinstance(op,dict):
            format_error(inpname,'operation entry {} not a dictionary'.format(operation))
        opname = op["name"]
        out.write("\n# operation: {}\n".format(operation))
        out.write("object {} = {{\n".format(operation_name(op)))
        out.write("\n    action {}".format(request_name(op)))
        if "input" in op:
            param = op["input"]
            ty = get_ref_or_type("input",opname,param)
            out.write("(\n")
            out.write('        {} : {}'.format("input",ty))
            if "description" in param:
                out.write(' # {}'.format(param["description"]))
            out.write('\n')
            out.write('    )')
        out.write('\n')
        responses = []
        if "output" in op:
            responses.append(op["output"])
        if "errors" in op:
            responses.extend(op["errors"])
        for resp in responses:
            ty = get_ref_or_type(opname,opname,resp)
            out.write('\n    action {}(val:{})\n'.format(response_name(op,resp["shape"]),ty))
        out.write("}\n")
    

    # Generate implementation boilerplate

    out.write(
"""
<<< impl
#include <aws/core/Aws.h>
#include <aws/s3/S3Client.h>
#include <sstream>

std::shared_ptr<Aws::IOStream> blob_to_iostream(const `blob` &data) {
    Aws::String s;
    s.insert(s.begin(),data.begin(),data.end());
    Aws::IOStream *x = new Aws::StringStream(s);
    std::shared_ptr<Aws::IOStream> y(x);
    return y;
}

Aws::Map<Aws::String, Aws::String> map_to_aws(`unordered_map[string][string]` map) {
    Aws::Map<Aws::String, Aws::String> res;
    for(auto it=map.begin(), en=map.end(); it != en; ++it){
        res[it->first.c_str()] = it->second.c_str();
    }
    return res;
}

>>>
<<< init 
{
    Aws::SDKOptions options;
    Aws::InitAPI(options);
}
>>>
"""
    )

    for operation,op in operations.iteritems():
        if "input" in op and operation not in missing_headers: 
            out.write("\n\n<<< impl\n")
            out.write("#include <aws/s3/model/{}Request.h>\n".format(operation))
            out.write(">>>\n")
        out.write("\n\nimplement {}.{} {{\n".format(operation_name(op),request_name(op)))
        out.write("    <<<\n")
        out.write("    Aws::Client::ClientConfiguration config;\n")
        out.write("    Aws::S3::S3Client s3_client(config);\n")
        if "input" in op:
            input_shape = op["input"]["shape"]
            out.write("    Aws::S3::Model::{} request;\n".format(input_shape))
            input_fields = defs[input_shape]["members"]
            input_req = defs[input_shape].get("required",None)
            for name,df in input_fields.iteritems():
                inp_fld = "input.{}_".format(iname(name))
                if input_req is None or name in input_req:
                    out.write("    request.Set{}({});\n".format(name,to_aws(inp_fld,df)))
                else:
                    out.write("    if ({}.size()) {{\n".format(inp_fld))
                    out.write("        request.Set{}({});\n".format(name,to_aws(inp_fld+"[0]",df)))
                    out.write("    }\n")
            out.write("    Aws::S3::Model::{}Outcome outcome = s3_client.{}(request);\n".format(operation,operation));
        else:
            out.write("        Aws::S3::Model::{}Outcome outcome = s3_client.{}();\n".format(name,name));
        if "output" in op:
            out.write("    if (outcome.IsSuccess()) {\n")
            out.write("        auto result = outcome.GetResultWithOwnership();\n")
            output_shape = op["output"]["shape"]
            output_fields = defs[output_shape]["members"]
            output_req = defs[output_shape].get("required",None)
            out.write("        `{}` res;\n".format(iname(output_shape)))
            for name,df in output_fields.iteritems():
                out_fld = 'res.{}_'.format(iname(name))
                res_fld = "result.Get{}()".format(name)
                if output_req is None or name in output_req:
                    out.write("        {}".format(from_aws(out_fld,res_fld,df)))
                else:
                    out.write("        if (result.{}HasBeenSet()) {{\n".format(name))
                    out.write("            out_fld.resize(1);\n")
                    out.write("            {}".format(from_aws(out_fld+"[0]",res_fld,df)))
                    out.write("        }\n")
            out.write("        `{}.{}`(res);\n".format(operation_name(op),response_name(op,output_shape)))
            out.write("    }}\n".format())
        out.write("    >>>\n")
        out.write("}}\n".format())
            
if __name__ == "__main__":
    main()
