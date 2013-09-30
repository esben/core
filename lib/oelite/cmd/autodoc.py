import oebakery
import oelite
import oelite.parse.docparse

import bb.utils

import logging
import os
import glob

description = "Generate documentation files from source code"
arguments = (
    ("layer", "Metadata layer(s) to generate documentation for", 0),
)

def add_parser_options(parser):
    parser.add_option(
        '-d', '--debug', action='store_true', default=False,
        help="Verbose output")
    return

def parse_args(options, args):
    if options.debug:
        logging.getLogger().setLevel(logging.DEBUG)
    else:
        logging.getLogger().setLevel(logging.INFO)
    options.layers = args
    return

def run(options, args, config):
    logging.debug("autodoc.run %s", options)
    meta = oelite.meta.DictMeta(meta=config)
    def parse(filename, name, output_file, meta):
        logging.debug("autodoc parsing %s", filename)
        parser = oelite.parse.docparse.DocParser(meta=meta)
        doc = parser.docparse(os.path.abspath(filename), name)
        bb.utils.mkdirhier(os.path.dirname(output_file))
        with open(output_file, 'w') as output:
            output.write(doc.get_asciidoc())
    for layer in options.layers:
        if not os.path.exists(layer):
            logging.error("No such layer: %s", layer)
            continue
        output_dir = os.path.join(layer, 'doc', 'auto')
        for f in glob.glob(os.path.join(layer, 'recipes/*/*.oe')):
            name = os.path.basename(f[:-3])
            recipe_meta=meta.copy()
            if '_' in name:
                name, version = name.split('_', 1)
                recipe_meta['PN'] = name
                recipe_meta['PV'] = version
                name = " ".join((name, version))
            else:
                recipe_meta['PN'] = name
                recipe_meta['PV'] = "0"
            output_file = os.path.join(
                output_dir, f[len(layer)+1:] + '.txt')
            parse(f, name, output_file, recipe_meta)
        for f in (glob.glob(os.path.join(layer, 'classes/*.oeclass')) +
                  glob.glob(os.path.join(layer, 'classes/*/*.oeclass'))):
            name = f[8:-7]
            class_meta=meta.copy()
            class_meta['PN'] = "unknown"
            recipe_meta['PV'] = "0"
            output_file = os.path.join(
                output_dir, f[len(layer)+1:] + '.txt')
            parse(f, name, output_file, class_meta)
