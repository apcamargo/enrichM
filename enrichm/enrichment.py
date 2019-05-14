#!/usr/bin/env python3
###############################################################################
#                                                                             #
#    This program is free software: you can redistribute it and/or modify     #
#    it under the terms of the GNU General Public License as published by     #
#    the Free Software Foundation, either version 3 of the License, or        #
#    (at your option) any later version.                                      #
#                                                                             #
#    This program is distributed in the hope that it will be useful,          #
#    but WITHOUT ANY WARRANTY; without even the implied warranty of           #
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the            #
#    GNU General Public License for more details.                             #
#                                                                             #
#    You should have received a copy of the GNU General Public License        #
#    along with this program. If not, see <http://www.gnu.org/licenses/>.     #
#                                                                             #
###############################################################################

__author__ = "Joel Boyd"
__copyright__ = "Copyright 2017"
__credits__ = ["Joel Boyd"]
__license__ = "GPL3"
__version__ = "0.0.7"
__maintainer__ = "Joel Boyd"
__email__ = "joel.boyd near uq.net.au"
__status__ = "Development"

from enrichm.comparer import Compare
from enrichm.draw_plots import Plot
from enrichm.databases import Databases
from enrichm.module_description_parser import ModuleDescription
from enrichm.parse_annotate import ParseAnnotate
from enrichm.parser import Parser
from enrichm.writer import Writer
from enrichm.matrix_generator import MatrixGenerator
from collections import Counter
from itertools import product, combinations, chain
from scipy import stats
import statsmodels.sandbox.stats.multicomp as sm
import multiprocessing as mp
import numpy as np
import re
import random
import os
import logging

################################################################################

def gene_fisher_calc(x):
    
    annotation, group_1, group_2 = x[0], x[1], x[2]
    
    dat = x[3:]
    
    if (dat[0][0]>0 or dat[1][0]>0) and (dat[0][1]>0 or dat[1][1]>0):
        score, pval = stats.fisher_exact(dat)
 
    else:
        score, pval = 'nan', 1.0

    return [annotation, group_1, group_2] + dat[0] + dat[1] + [score, pval]

def mannwhitneyu_calc(x):
    # Mann Whitney U test
    annotation, group_1, group_2, group_1_module_annotations, group_2_module_annotations = x
    group_1_module_annotations = group_1_module_annotations[0]
    group_2_module_annotations = group_2_module_annotations[0]

    if(sum(group_1_module_annotations)>0 and sum(group_2_module_annotations)>0):

        if(len(set(group_1_module_annotations)) == 1
            or
           len(set(group_2_module_annotations)) == 1):
            mw_t_stat, mw_p_value = 'NA', 1

        else:
            group_1_module_annotations = np.array(group_1_module_annotations)       
            group_2_module_annotations = np.array(group_2_module_annotations)           
            mw_t_stat, mw_p_value = \
                stats.mannwhitneyu(group_1_module_annotations,
                                         group_2_module_annotations)            
    else:
        mw_t_stat, mw_p_value = 'NA', 1

    return [annotation, group_1, group_2, str(np.mean(group_1_module_annotations)),
            str(np.mean(group_2_module_annotations)), mw_t_stat, mw_p_value]

def zscore_calc(x):
    
    annotation, group_1, group_2, group_1_module_annotations, group_2_module_annotations = x
    group_1_module_annotations = group_1_module_annotations[0]
    group_2_module_annotations = group_2_module_annotations[0]

    if len(group_1_module_annotations)>1:
        reference = group_1_module_annotations
        reference_name = group_1
        genome = group_2_module_annotations[0]
        genome_name = group_2
 
    else:
        reference_name = group_2
        reference = group_2_module_annotations
        genome = group_1_module_annotations[0]
        genome_name = group_1

    if genome>0:
        reference_group_comp_sd \
            = np.std(reference, axis=0)
        reference_group_comp_mean \
            = np.mean(reference, axis=0)

        if (genome-reference_group_comp_mean)>0:
   
            if reference_group_comp_sd==0:
                z_score = np.inf
                p_value = 0.0
     
            else:
                z_score = (genome-reference_group_comp_mean) / reference_group_comp_sd
                p_value = 2-2*stats.norm.cdf(z_score)

            return [annotation,
                    reference_name,
                    genome_name,
                    str(reference_group_comp_mean),
                    str(reference_group_comp_sd),
                    str(genome),
                    str(z_score), 
                    p_value]

################################################################################

class Enrichment:
    
    TIGRFAM                 = "tigrfam"
    PFAM                    = "pfam"
    KEGG                    = "kegg"
    CAZY                    = "cazy"
    EC                      = "ec"
    CLUSTER                 = "cluster"
    ORTHOLOG                = "ortholog"
    OTHER                   = "other"

    def __init__(self):

        self.TIGRFAM_PREFIX          = 'TIGR'
        self.PFAM_PREFIX             = 'PF'
        self.KEGG_PREFIX             = 'K'
        self.CAZY_PREFIX             = ["GH", "AA", "GT","PL","CE","CBM", "SLH", "dockerin", "cohesin", "GTCellulosesynt"]
        self.EC_PREFIX             = ["1", "2", "3","4","5","6", "7"]
        self.PROPORTIONS             = 'proportions.tsv'
        self.MODULE_COMPLETENESS     = 'modules.tsv'

    def check_annotation_type(self, annotations):
        '''
        Takes a random sample of the rownames from the input matrix
        and based on the characters they start with, determines the 
        type of annotation being used.
        
        Parameters
        ----------
        annotaitons     - List. A list of strings, each a rowname 
                          from the original input matrix

        Output
        ------
        The annotation type
        '''

        sample = random.sample(annotations, 1)[0]
        cazy_prefix = ''

        for character in list(sample):

            if character.isdigit()!=True:
            
                if character!='_':
                    cazy_prefix+=character

        if sample.startswith(self.TIGRFAM_PREFIX):
            return self.TIGRFAM
        elif sample.startswith(self.KEGG_PREFIX):
            return self.KEGG
        elif sample.startswith(self.PFAM_PREFIX):
            return self.PFAM
        elif cazy_prefix in self.CAZY_PREFIX:
            return self.CAZY
        elif sample.split('.')[0] in self.EC_PREFIX:
            return self.EC
        else:
            return self.OTHER
    
    def weight_annotation_matrix(self,
                                 sample_abundance,
                                 annotation_abundance,
                                 sample_dict,
                                 annotations):

        output_dict = {sample_group: dict() for sample_group in sample_dict.keys()}

        logging.info('Aggregating abundances across samples')
        for group, samples in sample_dict.items():
            output_dict[group] = dict()

            for annotation in annotations:
                output_dict[group][annotation] = list()

                for sample in samples:
                    sample_annotation_abundance = 0.0

                    for genome, genome_annotation_dict in annotation_abundance.items():

                        if annotation in genome_annotation_dict:
                            value = genome_annotation_dict[annotation]
                            
                            if genome in sample_abundance[sample]:
                                sample_annotation_abundance += sample_abundance[sample][genome]*value

                    output_dict[group][annotation].append(sample_annotation_abundance)
        
        return output_dict

    def calculate_portions(self,
                           modules,
                           combination_dict,
                           annotations_dict,
                           genome_list,
                           proportions_cutoff):
        '''
        Calculates the portions of genome

        Parameters
        ----------
        modules             - List. List of all possible annotations for the given annotation
                              type (eg, all ko ids, or all pfam ids). 
        combination_dict    - Dictionary. Metadata dictionary, with the groups as keys, and lists
                              of genomes as entries
        annotations_dict    - Dictionary. Annotation dictionary, with the the genome ids as keys,
                              and a list of annotations as the entry for each.  
        genome_list         - List. List of strings, each one a genome name
        proportions_cutoff  - Float. Value with which to cutoff
        '''
        raw_proportions_output_lines        = [['Module'] + list(combination_dict.keys())]

        for module in modules:
            
            module_values               = dict()
            raw_proportions_output_line = [module]
            
            for group_name, genome_list in combination_dict.items():
                if len(genome_list)>0:
                    coverage = len([genome for genome in genome_list 
                                    if module in annotations_dict[genome]])
                    total    = float(len(genome_list))
                    entry    = coverage/total
                    module_values[group_name] = entry
                    raw_proportions_output_line.append(str(entry))
                else:
                    raw_proportions_output_line.append('0.0')
            
            if max(module_values.values())>0:
                groups = combination_dict.keys()
                for group in groups:
                    group_val = module_values[group]
                    compare_groups = list()
                    if group_val>0:
                        for other_group in groups:
                            if other_group!=group:
                                other_group_val = module_values[other_group]
                                if other_group_val > 0:
                                    compare_value = group_val/other_group_val
                                else:
                                    compare_value = float("inf")
                                compare_groups.append(compare_value)
                    
                    if all([x>proportions_cutoff for x in compare_groups]):                    
                        pass 

            raw_proportions_output_lines.append(raw_proportions_output_line)

        return raw_proportions_output_lines

    def do(# Input options
           self, annotate_output, annotation_matrix, metadata_path, abundances_path, abundance_metadata_path,
           # Runtime options
           genomes_to_compare_with_group_file, pval_cutoff, proportions_cutoff, 
           threshold, multi_test_correction, batchfile, processes, allow_negative_values,
           ko, pfam, tigrfam, cluster, ortholog, cazy, ec, ko_hmm,
           # Output options
           output_directory):

        p  = Plot()
        database  = Databases()
        
        if genomes_to_compare_with_group_file:
            self.genomes_to_compare_with_group = Parser.parse_single_column_text_file(genomes_to_compare_with_group_file)
        else:
            self.genomes_to_compare_with_group = None
        
        if annotate_output:
            logging.info('Parsing annotate output: %s' % (annotate_output))
            pa = ParseAnnotate(annotate_output, processes)

            if ko:
                annotation_matrix = pa.ko
                gtdb_annotation_matrix = database.GTDB_KO
            elif ko_hmm:
                annotation_matrix = pa.ko_hmm
                gtdb_annotation_matrix = database.GTDB_KO
            elif pfam:
                annotation_matrix = pa.pfam
                gtdb_annotation_matrix = database.GTDB_PFAM
            elif tigrfam:
                annotation_matrix = pa.tigrfam
                gtdb_annotation_matrix = database.GTDB_TIGRFAM
            elif cluster:
                annotation_matrix = pa.cluster
                gtdb_annotation_matrix = None
            elif ortholog:
                annotation_matrix = pa.ortholog
                gtdb_annotation_matrix = None
            elif cazy:
                annotation_matrix = pa.cazy
                gtdb_annotation_matrix = database.GTDB_CAZY
            elif ec:
                annotation_matrix = pa.ec
                gtdb_annotation_matrix = database.GTDB_EC
        else:
                gtdb_annotation_matrix = None

        logging.info('Parsing annotations: %s' % annotation_matrix)
        annotations_dict, _, annotations, \
            = Parser.parse_simple_matrix(annotation_matrix)
        annotation_type = self.check_annotation_type(annotations)
        logging.info('Parsing metadata')
        metadata, metadata_value_lists, attribute_dict \
                    = Parser.parse_metadata_matrix(metadata_path)

        if abundances_path:
            
            logging.info('Parsing sample abundance')
            abundances_dict, _, _ = Parser.parse_simple_matrix(abundances_path)

            logging.info('Parsing sample metadata')
            _, _, ab_attribute_dict = Parser.parse_metadata_matrix(abundance_metadata_path)

            t = Test(annotations_dict,
                     None,
                     annotation_type,
                     threshold,
                     multi_test_correction,
                     processes,
                     database)
            
            weighted_abundance = self.weight_annotation_matrix(abundances_dict,
                                                 annotations_dict,
                                                 ab_attribute_dict,
                                                 annotations)

            results = t.test_weighted_abundances(weighted_abundance,
                                                 annotations)

            for result in results:
                test_result_lines, test_result_output_file = result

                test_result_output_path = os.path.join(output_directory,
                                                       test_result_output_file)
                Writer.write(test_result_lines, test_result_output_path)
                                                        
        else:
            if batchfile:
                genomes_set = set()
                batchfile_metadata, batchfile_metadata_value_lists, batchfile_attribute_dict \
                            = Parser.parse_metadata_matrix(batchfile)
                genomes_set = genomes_set.union(set(batchfile_metadata.keys()))
                reference_genome_annotations, genomes_set = Parser.filter_large_matrix(genomes_set, gtdb_annotation_matrix)

                annotations_dict.update(reference_genome_annotations)
                new_batchfile_attribute_dict = dict()
                for x,y in batchfile_attribute_dict.items():
                    s = [z for z in y if z in genomes_set]
                    if len(s)>0:
                        new_batchfile_attribute_dict[x] = s
                attribute_dict.update(new_batchfile_attribute_dict)
                batchfile_metadata={x:batchfile_metadata[x] for x in genomes_set}
                metadata.update(batchfile_metadata)
                batchfile_metadata_value_lists = set(new_batchfile_attribute_dict.keys())
                metadata_value_lists = metadata_value_lists.union(batchfile_metadata_value_lists)
            
            logging.info("Comparing sets of genomes")        
            combination_dict = dict()

            for combination in product(*list([metadata_value_lists])):
                genome_list = list()
            
                for genome, attributes in metadata.items():
            
                    for feature in combination:
            
                        if feature in attributes:
                            genome_list.append(genome)  
            
                combination_dict['_'.join(combination)] = genome_list

            t = Test(annotations_dict,
                    combination_dict,
                    annotation_type,
                    threshold,
                    multi_test_correction,
                    processes,
                    database)
            results = t.do(attribute_dict)

            for result in results:
                test_result_lines, test_result_output_file = result

                test_result_output_path = os.path.join(output_directory,
                                                    test_result_output_file)
                Writer.write(test_result_lines, test_result_output_path)

            raw_portions_path \
                = os.path.join(output_directory, self.PROPORTIONS)

            raw_proportions_output_lines \
                = self.calculate_portions(annotations, combination_dict, annotations_dict, genome_list, proportions_cutoff)

            Writer.write(raw_proportions_output_lines, raw_portions_path)

            logging.info('Generating summary plots')

            if annotation_type==self.KEGG:
                logging.info('Finding module completeness in differentially abundant KOs')
                
                for result_file in os.listdir(output_directory):
                
                    if(result_file.endswith("fisher.tsv") or result_file.endswith("cdf.tsv")):
                        p.draw_barplots(os.path.join(output_directory, result_file), pval_cutoff, output_directory)
                        
                        g1_sig_kos = set()
                        g2_sig_kos = set()
        
                        result_file_io = open(os.path.join(output_directory, result_file))
                        result_file_io.readline()
                        
                        for line in result_file_io:
                            sline = line.strip().split('\t')
                            if float(sline[-2])<pval_cutoff:
                                if result_file.endswith("fisher.tsv"):
                                    g1 = float(sline[3]) / (int(sline[3]) + int(sline[4]))
                                    g2 = float(sline[5]) / (int(sline[5]) + int(sline[6]))
                                elif result_file.endswith("cdf.tsv"):
                                    g1 = float(sline[3])
                                    g2 = float(sline[5])
                                if g1>g2:
                                    g1_sig_kos.add(sline[0])
                                else:
                                    g2_sig_kos.add(sline[0])
                        # TODO: below in function
                        module_output = [["Module", "Lineage", "Total steps", "Steps covered", "Percentage covered", "Module description"]]
                        for module, definition in database.m2def.items():
                            if module not in database.signature_modules:
                                pathway = ModuleDescription(definition)
                                num_all         = pathway.num_steps()
                                g1_num_covered, _, _, _ = pathway.num_covered_steps(g1_sig_kos)
                                g1_perc_covered    = g1_num_covered / float(num_all)
            
                                g2_num_covered, _, _, _ = pathway.num_covered_steps(g2_sig_kos)
                                g2_perc_covered    = g2_num_covered / float(num_all)
                                if g1_perc_covered>0:
                                    output_line = [module, sline[1], num_all, g1_num_covered, g1_perc_covered, database.m[module]]
                                    module_output.append(output_line)
                                if g2_perc_covered>0:
                                    output_line = [module, sline[2], num_all, g2_num_covered, g2_perc_covered, database.m[module]]
                                    module_output.append(output_line)
                        prefix = '_vs_'.join([sline[1], sline[2]]).replace(' ', '_')
                        Writer.write(module_output, os.path.join(output_directory, prefix +'_'+ self.MODULE_COMPLETENESS))   

            p.draw_pca_plot(annotation_matrix, metadata_path, output_directory)

class Test(Enrichment):
    
    FISHER_HEADER = [['annotation', 'group_1', 'group_2', 'group_1_true', 'group_1_false',
                      'group_2_true', 'group_2_false', 'score', 'pvalue', 'corrected_pvalue', 'description']]

    MANNWHITNEYU_HEADER =[['annotation', 'group_1', 'group_2', 'group_1_mean', 'group_2_mean',
                           'score', 'pvalue', 'corrected_pvalue', 'description']]
    
    ZSCORE_HEADER = [['annotation', 'group_1', 'group_2', 'group_1_mean', 'group_1_sd',
                      'group_2_count', 'score', 'pvalue', 'corrected_pvalue', 'description']]
    
    PA                     = 'presence_absence'
    IVG_OUTPUT             = 'ivg_results.cdf.tsv'
    GENE_FISHER_OUTPUT     = 'gvg_results.fisher.tsv'
    GVG_OUTPUT             = 'gvg_results.mannwhitneyu.tsv'
    
    mtc_dict = {'b': 'Bonferroni',
                's': 'Sidak',
                'h': 'Holm',
                'hs': 'Holm-Sidak',
                'sh': 'Simes-Hochberg',
                'ho': 'Hommel',
                'fdr_bh': 'FDR Benjamini-Hochberg',
                'fdr_by': 'FDR Benjamini-Yekutieli',
                'fdr_tsbh': 'FDR 2-stage Benjamini-Hochberg',
                'fdr_tsbky': 'FDR 2-stage Benjamini-Krieger-Yekutieli',
                'fdr_gbs': 'FDR adaptive Gavrilov-Benjamini-Sarkar'}
    
    def __init__(self, genome_annotations, groups, 
                 annotation_type, threshold, multi_test_correction, 
                 processes, database):
        '''
        Collects functions to count and test differential abundance among groups of genomes.
        '''

        self.threshold              = threshold
        self.multi_test_correction  = multi_test_correction
        self.annotation_type        = annotation_type
        self.groups                 = groups
        self.pool                   = mp.Pool(processes = processes)
        self.m2def                  = database.m2def
        self.m                      = database.m
        self.clan2pfam              = database.clan2pfam
        self.clan_to_description    = database.clan2name
        self.k                      = database.k
        self.tigrfamdescription     = database.tigrfamdescription
        self.pfam2description       = database.pfam2description
        self.ec2description         = database.ec2description
        
        if annotation_type==self.PFAM:
            self.genome_annotations = dict()
            for key, item in genome_annotations.items():                
                self.genome_annotations[key] = {key.split('.')[0]:entry for key,entry in item.items()}
        else:
            self.genome_annotations = genome_annotations

    def test_chooser(self, groups):
        groups = [len(x) for x in groups]
        
        # Enrichment
        if any(group == 1 for group in groups):
            enrichment_test = self.PA
            overrepresentation_test = stats.norm.cdf
            
        else:
            enrichment_test = stats.fisher_exact
            overrepresentation_test = stats.mannwhitneyu
        
        return enrichment_test, overrepresentation_test

    def correct_multi_test(self, pvalues):
        logging.info('Applying multi-test correction using the %s method' % (self.mtc_dict[self.multi_test_correction]) )
        corrected_pvals \
            = sm.multipletests(pvalues,
                               alpha        = self.threshold,
                               method       = self.multi_test_correction,
                               returnsorted = False,
                               is_sorted    = False)[1]

        return corrected_pvals

    def count(self, annotation, group, freq):

        if freq:
            group_true = list()

        else:
            group_true = 0
        
        group_false = 0

        for genome in self.groups[group]:
            if annotation in self.genome_annotations[genome]:
                if freq:
                    group_true.append(self.genome_annotations[genome][annotation])
                else:
                    if self.genome_annotations[genome][annotation]>0.0:                    
                        group_true+=1
                    else:
                        group_false+=1
                
            else:
        
                if freq:
                    group_true.append(0)

                else:
                    group_false+=1

        return group_true, group_false
        
    def gene_frequencies(self, group_1, group_2, freq=False):

        res_list    = list()
        annotations = set(chain(*self.genome_annotations.values()))

        for annotation in annotations:
            passed = True
            group_1_true, group_1_false \
                = self.count(annotation,
                              group_1,
                              freq)
            group_2_true, group_2_false \
                = self.count(annotation,
                              group_2,
                              freq)

            if freq:
                if(len([x for x in group_1_true if x!='0'])==0 and
                    len([x for x in group_2_true if x!='0'])==0 ):
                    passed = False
            else:
                if(group_1_true==0 and group_2_true==0):
                    passed = False
            
            if passed:
                res_list.append([annotation, group_1, group_2, [group_1_true, group_1_false], [group_2_true, group_2_false]])

        return res_list

    def corrected_pvals(self, output_lines):
        pvalues = [output_line[-1] for output_line in output_lines]
        corrected_pvalues = self.correct_multi_test(pvalues)

        return corrected_pvalues

    def add_descriptions(self, output_lines):
        if self.annotation_type == self.KEGG:
            desc = self.k

        if self.annotation_type == self.CAZY:
            desc = None

        if self.annotation_type == self.TIGRFAM:
            desc = self.tigrfamdescription

        if self.annotation_type == self.PFAM:
            desc = self.pfam2description
            
        if self.annotation_type == self.EC:
            desc = self.ec2description

        if self.annotation_type == self.OTHER:
            desc = None
        
        for line in output_lines:
            annotation = line[0]

            if desc:
            
                if annotation in desc:
                    line.append(desc[annotation])
            
                else:
                    line.append("NA")
            
            else:
                line.append("NA")
        
        return output_lines

    def test_weighted_abundances(self,
                                 weighted_abundance,
                                 annotations):

        logging.info('Calculating enrichment across samples using Mann-Whitney U test')
        results = list()

        for combination in combinations(weighted_abundance, 2):
            prefix = '_vs_'.join(
                [sorted(combination)[0], sorted(combination)[1]]).replace(' ', '_')
            res_list = list()

            for annotation in annotations:
                group_1 = weighted_abundance[combination[0]][annotation]
                group_2 = weighted_abundance[combination[1]][annotation]
                gene_count = [annotation, combination[0],
                              combination[1], [group_1], [group_2]]
                res_list.append(gene_count)

            output_lines = self.pool.map(mannwhitneyu_calc, res_list)

            for idx, corrected_pval in enumerate(self.corrected_pvals(output_lines)):
                output_lines[idx].append(str(corrected_pval))

            output_lines = self.add_descriptions(output_lines)
            output_lines = self.MANNWHITNEYU_HEADER + output_lines
            results.append([output_lines, prefix + '_' + self.GVG_OUTPUT])

        return results

    def do(self, group_dict):
        results = list()

        for combination in combinations(group_dict, 2):
            enrichment_test, overrepresentation_test = self.test_chooser( [group_dict[member] for member in combination] )
            prefix = '_vs_'.join([sorted(combination)[0], sorted(combination)[1]]).replace(' ', '_')
            
            logging.info('Comparing gene frequency among groups: %s' % ', '.join(combination))
            
            if enrichment_test == stats.fisher_exact:
                logging.info('Testing gene enrichment using Fisher\'s exact test')    
                gene_count = self.gene_frequencies(*combination)
                output_lines = self.pool.map(gene_fisher_calc, gene_count)
            
                for idx, corrected_pval in enumerate(self.corrected_pvals(output_lines)):
                    output_lines[idx].append(str(corrected_pval))
                
                header = self.FISHER_HEADER
                output = self.GENE_FISHER_OUTPUT
                output_lines = self.add_descriptions(output_lines)
                output_lines = header + output_lines
                results.append([output_lines, prefix +'_'+ output])
            
            elif enrichment_test == self.PA:
                logging.info('enrichment statistics not possible with only one genome to compare')
                logging.info('See prevalence matrix for unique genes in groups')

            logging.info('Comparing gene over-representation among genomes')
            
            if overrepresentation_test == stats.mannwhitneyu:
                logging.info('Testing over-representation using Mann-Whitney U test')
                gene_count = self.gene_frequencies(*combination, True)
                output_lines = self.pool.map(mannwhitneyu_calc, gene_count)

                for idx, corrected_pval in enumerate(self.corrected_pvals(output_lines)):
                    output_lines[idx].append(str(corrected_pval))
                
                header = self.MANNWHITNEYU_HEADER
                output = self.GVG_OUTPUT

            elif overrepresentation_test == stats.norm.cdf:
                logging.info('Testing over-representation using Z score test')
                gene_count = self.gene_frequencies(*combination, True)
                output_lines = self.pool.map(zscore_calc, gene_count)
                output_lines = [x for x in output_lines if x]
                
                for idx, corrected_pval in enumerate(self.corrected_pvals(output_lines)):
                    output_lines[idx].append(str(corrected_pval))
                
                header = self.ZSCORE_HEADER
                output = self.IVG_OUTPUT
            
            output_lines = self.add_descriptions(output_lines)
            output_lines = header + output_lines
            results.append([output_lines, prefix +'_'+ output])

        return results
