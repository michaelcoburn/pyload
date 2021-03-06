#!/usr/bin/env python
# coding: utf-8

import sys
import getopt
import os
import logging
import re
import hashlib
import csv
import json
import time
import collections

from json import dumps, loads, JSONEncoder, JSONDecoder
import pickle

### configure logging
level = logging.DEBUG
format = '%(asctime)s - %(message)s'
handlers = [logging.FileHandler('test.log'), logging.StreamHandler()]
logging.basicConfig(level=level, format=format, handlers=handlers)


class fingerprint():

    # def __init__(self):
    #     self.final_dict = {}



    def write_file(self, filename, data_to_csv):
        with open(filename, mode='a') as csv_file:
            #fieldnames = ['trxid', 'query']
            writer = csv.writer(csv_file, delimiter=',', quotechar='"', quoting=csv.QUOTE_MINIMAL)
            # writer.writeheader()
            writer.writerow(data_to_csv)

            # for key, value in data.items():
            #    writer.writerow(value)

    def createFingerprint(self, trxid, hash, query, result_csv, debug, trxid_seq):
        variable_counter = 1
        myvalues = {}
        #myvalues = collections.OrderedDict()

        self.trxid_seq = trxid_seq
        self.hash = hash
        self.query = ' '.join(query.split())
        self.result_csv = result_csv
        self.origingal_query = self.query
        self.trxid = trxid
        self.debug = debug
        self.new_hash = False
        self.hash_query_list = 0

        if self.debug:
            logging.debug(self.query )

        # Between-And
        #query_between = re.search(r'(?i)(WHERE(.*))BETWEEN(.*)AND(\'|\")?(\s\S*)(\'|\")?((;| )(.*))$', query)
        query_between = re.search(r'(?i)(WHERE(.*))BETWEEN (.*) AND ([\d]+|(\'|\")(.*)(\'|\"))(.*)$', self.query)
        if query_between:
            # if value starts with a number and contains - or : it is a date
            # we generate a different hash for that
            if re.match(r"^\"\d+[-:]", query_between.group(4)):
                self.new_hash = True

            # we are using two sub to have different variable counters
            self.query = re.sub(r'(?i)(WHERE(.*))BETWEEN(.*)AND',
                           rf'\1BETWEEN <v{variable_counter}> AND {query_between.group(4)} ', self.query)
            if f'v{variable_counter}' not in myvalues:
                myvalues[f'v{variable_counter}'] = set()
                myvalues[f'v{variable_counter}'].add(query_between.group(3))
                variable_counter += 1

            self.query = re.sub(r'(?i)(WHERE(.*))BETWEEN(.*)AND(.*)',
                           rf'\1 BETWEEN \3 AND <v{variable_counter}> {query_between.group(8)}',
                           self.query)
            if f'v{variable_counter}' not in myvalues:
                myvalues[f'v{variable_counter}'] = set()
                myvalues[f'v{variable_counter}'].add(query_between.group(4))
                variable_counter += 1

        # If it is an INSERT|REPLACE INTO VALUES
        query_matches = re.search(r'(?i)(INSERT|REPLACE) INTO', self.query)
        if query_matches:
            while True:
                query_matches = re.search(r'(?i)(VALUES).\((.*)\)', self.query)
                if query_matches:
                    self.query = re.sub(r'(?i)(VALUES).\((.*)\)', rf'\1 <v{variable_counter}>', self.query, 1)

                    if f'v{variable_counter}' not in myvalues:
                        myvalues[f'v{variable_counter}'] = set()
                    myvalues[f'v{variable_counter}'].add(query_matches.group(2))
                    variable_counter += 1
                else:
                    break

        # If it is an SELECT ... IN ()
        query_matches = re.search(r'(?i)WHERE(.*?)IN\s+\((.*?)\)', self.query)
        if query_matches:
            while True:
                query_matches = re.search(r'(?i)(IN)\s+\((.*?)\)', self.query)
                if query_matches:
                    self.query = re.sub(r'(?i)(IN)\s+(\()(.*?)(\))(\)+)?(.*?)', rf'\1 <v{variable_counter}>\5 \6', self.query, 1)
#                    query = re.sub(r'(?i)(IN).*?\((.*?)\)(.*)', rf'\1 <v{variable_counter}>\3', query, 1)

                    if f'v{variable_counter}' not in myvalues:
                        myvalues[f'v{variable_counter}'] = set()
                    myvalues[f'v{variable_counter}'].add(query_matches.group(2))
                    variable_counter += 1
                else:
                    break

        query_matches = re.search(r'(?i)^update.(.*).(SET)\s(.*?)((\swhere|;)(.*))', self.query)
        if query_matches:
            setlist = re.search(r'(?i)(update.*\s+SET\b\s+)(.*?)(\s+where(?!.*where)|$)', self.query)
            set_split = list(finger.mysplit(setlist.group(2)))
            # Using enumerate()
            for v, i in enumerate(set_split):
                item = i.split('=', 1)
                #if values is equal with the variable plus an intiger, that's incrementing so we do not change it
                isincrement = re.match(rf'{item[0]} *\+ *\d', item[1])
                if isincrement:
                    set_split[v] = item[0] + "=" + item[1]

                else:
                    if f'v{variable_counter}' not in myvalues:
                        myvalues[f'v{variable_counter}'] = set()
                    myvalues[f'v{variable_counter}'].add(item[1])
                    item[1] = f'<v{variable_counter}>'
                    set_split[v] = item[0] + "=" + item[1]
                    variable_counter += 1

            self.query = ('{}{} {}'.format(
                 setlist.group(1),
                 ', '.join(set_split),
                 setlist.group(3)
             ))

        # where values is a simple number
        query_matches = re.search(r'(=|<>|>|<)(\s+)?([\d]+)', self.query)
        # if it matches we go trough the whole line and replace all matches but we increase the counter as well.
        # SELECT c FROM sbtest1 WHERE id=23 and bela=29 and lajos="fsdfsf";
        # SELECT c FROM sbtest1 WHERE id=<v1> and bela=<v2> and lajos=v3;
        if query_matches:
            while True:
                query_matches = re.search(r'(=|<>|>|<)(\s+)?([\d]+)', self.query)
                if query_matches:
                    self.query = re.sub(r'(=|<>|>|<)(\s+)?([\d]+)', rf'\1 <v{variable_counter}>', self.query, 1)
                    if f'v{variable_counter}' not in myvalues:
                        myvalues[f'v{variable_counter}'] = set()
                    myvalues[f'v{variable_counter}'].add(query_matches.group(3))
                    variable_counter += 1
                else:
                    break

        # everything between '' and ""
        query_matches = re.search(r'(\'|\")(.*?)(\'|\")', self.query)
        if query_matches:
            while True:
                query_matches = re.search(r'(\'|\")(.*?)(\'|\")', self.query)
                if query_matches:
                    self.query = re.sub(r'(\'|\")(.*?)(\'|\")', rf'<v{variable_counter}>', self.query,1)
                    if f'v{variable_counter}' not in myvalues:
                        myvalues[f'v{variable_counter}'] = set()
                    myvalues[f'v{variable_counter}'].add(query_matches.group(2))
                    variable_counter += 1
                else:
                    break

        if self.debug:
            logging.debug(self.query)
        # we generate a hash we add trx_id to the query as well because the same query can be part of multiple transactions as well.
        # with this they will have a different hash but queries outside of a transactions trx_id=0 will have the same hash
        # if there is a date in between , we generate a different hash
        if self.new_hash:
            self.hash_query = self.query + str(self.trxid) + "date"
            self.hash_obj_trx = hashlib.md5(self.hash_query.encode())
            self.hash_finger = self.query + "date"
            self.hash_obj = hashlib.md5(self.hash_finger.encode())
        else:
            self.hash_query = self.query + str(self.trxid)
            self.hash_obj_trx = hashlib.md5(self.hash_query.encode()).hexdigest()
            self.hash_finger = self.query
            self.hash_obj = hashlib.md5(self.hash_finger.encode()).hexdigest()


        self.temp_dict = {}
        self.temp_dict = {self.hash_obj_trx: {
            'trxid': {0},
            'trxid_seq': {0},
            'orig_hash': {0},
            'orig_query': {None},
            'finger_hash': {0},
            'finger_hash_trx': {0},
            'fingerprint': {None},
            'hash_query_list': {0},
            'values' : {None}
        }}
        self.temp_dict[self.hash_obj_trx]['trxid'] = self.trxid
        self.temp_dict[self.hash_obj_trx]['trxid_seq'] = self.trxid_seq
        self.temp_dict[self.hash_obj_trx]['orig_hash'] = self.hash
        self.temp_dict[self.hash_obj_trx]['orig_query'] = self.origingal_query
        self.temp_dict[self.hash_obj_trx]['finger_hash'] = self.hash_obj
        self.temp_dict[self.hash_obj_trx]['finger_hash_trx'] = self.hash_obj_trx
        self.temp_dict[self.hash_obj_trx]['fingerprint'] = self.query
        self.temp_dict[self.hash_obj_trx]['hash_query_list'] = self.hash_query_list
        self.temp_dict[self.hash_obj_trx]['values'] = myvalues


        # self.trxid_dict = { self.trxid: {
        #  'transactions': {}
        # }}
        #
        # self.trxid_dict[self.trxid]['transactions'] = self.hash_obj_trx
        #

        # if hash_obj.hexdigest() not in self.final_dict:
        #     self.temp_dict = {}
        #     self.temp_dict = {hash_obj.hexdigest(): {
        #         'trxid': {0},
        #         'trxid_seq': {0},
        #         'orig_hash': {0},
        #         'orig_query': {None},
        #         'fingerprint' : {None},
        #         'values' : {None}
        #     }}
        #     self.temp_dict[hash_obj.hexdigest()]['trxid'] = self.trxid
        #     self.temp_dict[hash_obj.hexdigest()]['trxid_seq'] = self.trxid_seq
        #     self.temp_dict[hash_obj.hexdigest()]['orig_hash'] = self.hash
        #     self.temp_dict[hash_obj.hexdigest()]['orig_query'] = self.origingal_query
        #     self.temp_dict[hash_obj.hexdigest()]['fingerprint'] = self.query
        #     self.temp_dict[hash_obj.hexdigest()]['values'] = myvalues
        #     self.final_dict.update(self.temp_dict)
        # else:
        #     self.temp_dict = {}
        #     self.temp_dict = {hash_obj.hexdigest(): {
        #         'trxid': {0},
        #         'trxid_seq': {0},
        #         'orig_hash': {0},
        #         'orig_query': {None},
        #         'fingerprint' : {None},
        #         'values' : {None}
        #     }}
        #     self.temp_dict[hash_obj.hexdigest()]['trxid'] = self.trxid
        #     self.temp_dict[hash_obj.hexdigest()]['trxid_seq'] = self.trxid_seq
        #     self.temp_dict[hash_obj.hexdigest()]['orig_hash'] = self.hash
        #     self.temp_dict[hash_obj.hexdigest()]['orig_query'] = self.origingal_query
        #     self.temp_dict[hash_obj.hexdigest()]['fingerprint'] = self.query
        #     self.temp_dict[hash_obj.hexdigest()]['values'] = myvalues
        #     finger.merge_dict(self.final_dict, self.temp_dict)

        # hash_obj = hashlib.md5(query.encode())
        data = []
        data.append(self.trxid)
        data.append(self.trxid_seq)
        data.append(self.hash)
        data.append(self.hash_obj)
        data.append(self.hash_obj_trx)
        data.append(self.origingal_query)
        data.append(self.query)
        data.append(myvalues)
        finger.write_file(result_csv, data)
        return self.temp_dict

    def save_dict(self, dict):
        self.dict = dict
        for key in dict.keys():

            data_csv = []
            data_csv.append(key)
            data_csv.append(self.dict[key]['trxid'])
            data_csv.append(self.dict[key]['trxid_seq'])
            data_csv.append(self.dict[key]['finger_hash'])
            data_csv.append(self.dict[key]['finger_hash_trx'])
            data_csv.append(self.dict[key]['hash_query_list'])
            data_csv.append(self.dict[key]['orig_query'])
            data_csv.append(self.dict[key]['fingerprint'])
            data_csv.append(self.dict[key]['values'])
            finger.write_file("queries.grouped.csv", data_csv)

    def mysplit(self,text):
        in_quotes = False
        fragment = ''
        escape = False
        for ch in text:
            if "\\" in ch:
                escape = True
            elif ch in ("'", '"') and escape:
                fragment += ch
                escape = False
            elif ch == ',' and not in_quotes:
                yield fragment
                fragment = ''
                escape = False
            else:
                fragment += ch
                if ch == in_quotes:
                    in_quotes = False
                    escape = False
                elif ch in ("'", '"'):
                    in_quotes = ch
                    escape = False
        yield fragment

    def merge_dict(self,dict1, dict2):
        for k in dict2:
            for v in dict2[k]['values']:
                dict1[k]['values'][v].update(dict2[k]['values'][v])

    def write_dict(self):
        with open('pyload_query_dictionary.csv', 'w', newline="") as csv_file:
            writer = csv.writer(csv_file)
            for key, value in self.final_dict.items():
                writer.writerow([key, value])


class readData():

    def __init__(self):
        # finding all queries and they could start with a comment as well
        self.regex = "(?i)^(\/\*(.*)\*\/)?( |)(select|update|insert|delete|replace|commit|begin|start transaction|SET autocommit)"
        self.splitstring = "# Time: "
        self.trx_order_id = 0
        self.count = 1
        self.query_values = ""
        self.trxid = 0
        self.re_trx_id = re.compile(r'^# InnoDB_trx_id: (.*)')
        self.stop_list = "(?i)^(set timestamp=|SELECT @@version|SHOW GLOBAL STATUS|use(.*);|set session |set global)"

    def openFile(self, slowlogFile, debug):
        self.debug = debug
        if os.path.exists(slowlogFile):
            with open(slowlogFile, 'r') as f:
                try:
                    if self.debug:
                        logging.debug(f"{slowlogFile} is opend.")
                    filecontent = f.readlines()
                    return filecontent

                except:
                    logging.critical("Could not Open the file!")
        else:
            if debug:
                if self.debug:
                    logging.info("Slow log file does not exists!")

    def parseSlowLog(self, slowlogFile, debug):
        # read the file into filecontent
        self.slow_dictionary = {}
        #self.slow_dictionary = collections.OrderedDict()

        self.debug = debug
        # we need i to be able to keep the sequence of the queries in a transaction
        # which query has higher seq number should be executed later
        self.i = 1
        filecontent = readC.openFile(slowlogFile, self.debug)
        # find first # Time: 2020-01-21T16:55:13.249612Z
        #for lines in readC.filter_output_between_strings(filecontent, self.splitstring):
        for lines in readC.get_queries(filecontent):
            self.trxid = lines[0]
                #if trxid != "0":
                #    logging.info(f"This is part of a transaction: {trxid}")

            if re.match(self.regex, lines[1]) is not None:
                query = lines[1]
                query_text = query
                if re.match(r'(?i)(\/\*(.*)\*\/)', query):
                    query_text = re.sub(r'(?i)(\/\*(.*)\*\/)', rf'', query)
                hash_text = query_text + str(self.i)
                hash_obj = hashlib.md5(hash_text.encode()).hexdigest()
                #if hash_obj.hexdigest() not in self.slow_dictionary:
                temp_dict = {hash_obj: {
                    'trxid': {0},
                    'trxid_seq': {0},
                    'orig_query': {None}
                }}
                temp_dict[hash_obj]['trxid'] = self.trxid
                temp_dict[hash_obj]['trxid_seq'] = self.i
                temp_dict[hash_obj]['orig_query'] = query_text
                self.slow_dictionary.update(temp_dict)
            self.i += 1

        return(self.slow_dictionary)


    def filter_output_between_strings(self, listLog, separator):
        result = []
        sublist = []
        for x in listLog:
            if separator in x:
                if sublist:
                    result.append(sublist)
                sublist = []
            else:
                sublist.append(x)
        result.append(sublist)
        return result

    def get_queries(self, filecontent):
        query = []
        trx_id = 0

        for line in filecontent:
            if line.startswith('# Time:') or line.startswith('# User@Host:'):
                if query:
                    yield trx_id, ' '.join(query)
                    # if we found a query we reset the transaction ID
                    trx_id = 0
                query = []
            elif line.startswith('# InnoDB_trx_id'):
                m = self.re_trx_id.match(line)
                trx_id = str(m.group(1))
            #elif line.startswith('#') or line.lower().startswith('set timestamp'):
            elif line.startswith('#') or re.match(self.stop_list, line):
                continue
            else:
                query.append(line.strip())
        yield trx_id, ' '.join(query)

class SetEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, set):
            return list(obj)
        return json.JSONEncoder.default(self, obj)

def main(argv):
    slowlogFile = ''
    debug = 0
    final_dict = {}
    #final_dict = collections.OrderedDict()

    trx_dict = {}
    #trx_dict = collections.OrderedDict()

    tmp_dict = {}
    #tmp_dict = collections.OrderedDict()

    no_trx_dict = {}
    #no_trx_dict = collections.OrderedDict()

    trx_list = []

    message = """Usage:
    Process SlowLog File: pyLoad.py -i <slowlogFile>
    """
    try:
        opts, args = getopt.getopt(argv, "hi:d", ["slowlogFile=", "debug"])
    except getopt.GetoptError:
        print(message)
        sys.exit(2)
    for opt, arg in opts:
        if opt == '-h':
            print(message)
            sys.exit()
        elif opt in ("-i", "--slowlogFile"):
            slowlogFile = arg
        elif opt in ("-d", "--debug"):
            debug = 1

    if slowlogFile:
        result_csv = "queries.csv"
        queries_dcitionary = readC.parseSlowLog(slowlogFile, debug)
        line_count = 0

        for k in queries_dcitionary.keys():
            #print(f"Transaction ID = {queries_dcitionary[k]['trxid']}, Query = {queries_dcitionary[k]['orig_query']}")
            if debug:
                logging.debug(f"Transaction ID = {queries_dcitionary[k]['trxid']}, Query = {queries_dcitionary[k]['orig_query']}")
            if queries_dcitionary[k]['trxid'] == "0":
                no_trx_dict.update(finger.createFingerprint(trxid=queries_dcitionary[k]['trxid'], trxid_seq=queries_dcitionary[k]['trxid_seq'], query=queries_dcitionary[k]['orig_query'], hash=k, result_csv=result_csv, debug=debug))
                hash_trx = list(no_trx_dict.keys())[0]
                if hash_trx not in final_dict.keys():
                    final_dict.update(no_trx_dict)
                    del no_trx_dict[hash_trx]
                elif no_trx_dict[hash_trx]['trxid'] == queries_dcitionary[k]['trxid'] and final_dict[hash_trx]['finger_hash'] == no_trx_dict[hash_trx]['finger_hash']:
                    for v in no_trx_dict[hash_trx]['values']:
                        final_dict[hash_trx]['values'][v].update(no_trx_dict[hash_trx]['values'][v])

                    del no_trx_dict[hash_trx]

            elif queries_dcitionary[k]['trxid'] != "0" and re.match(r"(?i)^(\s+)?(begin|start transaction|SET autocommit(\s+)?=(\s+)?0)(\s+)?;$",queries_dcitionary[k]['orig_query']):
                if debug:
                    logging.debug(f"Start Transaction = {queries_dcitionary[k]['trxid']}")
                tmp_dict.update(finger.createFingerprint(trxid=queries_dcitionary[k]['trxid'], trxid_seq=queries_dcitionary[k]['trxid_seq'], query=queries_dcitionary[k]['orig_query'], hash=k, result_csv=result_csv, debug=debug))
            elif queries_dcitionary[k]['trxid'] != "0" and re.match("(?i)^(\/\*(.*)\*\/)?( |)(select|update|insert|delete|replace)", queries_dcitionary[k]['orig_query']):
                result = finger.createFingerprint(trxid=queries_dcitionary[k]['trxid'], trxid_seq=queries_dcitionary[k]['trxid_seq'], query=queries_dcitionary[k]['orig_query'], hash=k, result_csv=result_csv, debug=debug)
                tmp_dict.update(result)
                ## trx_dict dictionary holds all the query hashes from that transaction
                if queries_dcitionary[k]['trxid'] not in trx_dict:
                    trx_dict[queries_dcitionary[k]['trxid']] = []
                #print(trx_dict)
                #print(f"++++++ {list(result.keys())}")
                if list(result.keys())[0] not in trx_dict[queries_dcitionary[k]['trxid']]:
                    trx_dict[queries_dcitionary[k]['trxid']].append(list(result.keys())[0])
                #print(f"%%%%%%%%% {tmp_dict}")
                #print(f"===== {trx_dict}")
            # if the there is a commit we collect all the queries from that transaction and copy them
            # over to the final dictionary
            elif queries_dcitionary[k]['trxid'] != 0 and re.match(r"(?i)^(\s+)?(commit|rollback|SET autocommit(\s+)?=(\s+)?1)(\s+)?;$", queries_dcitionary[k]['orig_query']):
                result = finger.createFingerprint(trxid=queries_dcitionary[k]['trxid'], trxid_seq=queries_dcitionary[k]['trxid_seq'], query=queries_dcitionary[k]['orig_query'], hash=k, result_csv=result_csv, debug=debug)
                tmp_dict.update(result)
                # we create a hash from all of the queries from the transactions and store the hash in this list
                # this is how we know if we already has a simliar transaction or not. If we have one we will not save it.
                # if it is not in the list we put it there and copy the queries to the final dictionary
                if debug:
                    logging.debug(f"Committed transaction = {queries_dcitionary[k]['trxid']}")
                trx_query_list = []

                if queries_dcitionary[k]['trxid'] not in trx_dict:
                    trx_dict[queries_dcitionary[k]['trxid']] = []
                #print(trx_dict)
                if list(result.keys())[0] not in trx_dict[queries_dcitionary[k]['trxid']]:
                    trx_dict[queries_dcitionary[k]['trxid']].append(list(result.keys())[0])

                #print(f"55555555 {trx_dict[queries_dcitionary[k]['trxid']]}")

                #print(f"--- {trx_dict[queries_dcitionary[k]['trxid']]}")
                for tmp_hash_trx in trx_dict[queries_dcitionary[k]['trxid']]:
                    #print(tmp_hash_trx)
                    # collecting all the queries from that transaction
                    try:
                        if tmp_dict[tmp_hash_trx]['trxid'] == queries_dcitionary[k]['trxid']:
                            trx_query_list.append(tmp_dict[tmp_hash_trx]['fingerprint'])
                    except:
                        #print(f"tmp_dict {tmp_dict}")
                        print(f"result {result}")
                        print(f"trx_dict[queries_dcitionary[k]['trxid']] {trx_dict[queries_dcitionary[k]['trxid']]}")
                        print(f"tmp_hash_trx {tmp_hash_trx}")
                        print(f"queries_dcitionary[k] {queries_dcitionary[k]}")
                        print(f"tmp_dict[tmp_hash_trx] {tmp_dict[tmp_hash_trx]}")


                # creating the hash
                hash_query_list = hashlib.md5(str(trx_query_list).encode()).hexdigest()

                for tmp_hash_trx in trx_dict[queries_dcitionary[k]['trxid']]:
                    # collecting all the queries from that transaction
                    if tmp_dict[tmp_hash_trx]['trxid'] == queries_dcitionary[k]['trxid']:
                        tmp_dict[tmp_hash_trx].update({'hash_query_list': hash_query_list})


                # print(trx_query_list)
                # print(hash_query_list.hexdigest())
                # if hash not in the list add it and to the dictionary

                if hash_query_list not in trx_list:
                    for tmp_hash_trx in trx_dict[queries_dcitionary[k]['trxid']]:
                        if tmp_dict[tmp_hash_trx]['trxid'] == queries_dcitionary[k]['trxid']:
                            #print(f"----------- {final_dict}")
                            final_dict[tmp_hash_trx] = {}
                            #final_dict[tmp_hash_trx] = collections.OrderedDict()

                            final_dict[tmp_hash_trx].update(tmp_dict[tmp_hash_trx])
                            final_dict[tmp_hash_trx].update({'hash_query_list': hash_query_list})
                    del tmp_dict[tmp_hash_trx]
                    trx_list.append(hash_query_list)
                    #print(trx_list)
                else:
                    for key in final_dict.keys():
                        t = time.process_time()
                        if final_dict[key]['hash_query_list'] == hash_query_list:
                            new_trx_hash = final_dict[key]['fingerprint'] + queries_dcitionary[k]['trxid']
                            new_trx_hash = hashlib.md5(new_trx_hash.encode()).hexdigest()
                            #print(f"vegre {tmp_dict[new_trx_hash]}")
                            for v in tmp_dict[new_trx_hash]['values']:
                                final_dict[key]['values'][v].update(tmp_dict[new_trx_hash]['values'][v])
                        elapsed_time = time.process_time() - t
                        #print(f"{len(tmp_dict)} - {elapsed_time}")



                    # #print(trx_dict[queries_dcitionary[k]['trxid']])
                    # for tmp_hash_trx in trx_dict[queries_dcitionary[k]['trxid']]:
                    #     if tmp_dict[tmp_hash_trx]['hash_query_list'] == queries_dcitionary[k]['trxid']:
                    #         #print(final_dict)
                    #         print(tmp_hash_trx)
                    #         print(queries_dcitionary[k]['trxid'])
                    #         print(queries_dcitionary[k]['orig_query'])
                    #         print(f";;;;;; {final_dict.keys()}")
                    #         print(trx_dict)
                    #         print(tmp_dict)
                    #         print(final_dict)
                    #
                    #         #print(final_dict)
                    #         for v in tmp_dict[tmp_hash_trx]['values']:
                    #              final_dict[tmp_hash_trx]['values'][v].update(tmp_dict[tmp_hash_trx]['values'][v])
                    #


                    # for key in final_dict.keys():
                    #     t = time.process_time()
                    #     if final_dict[key]['hash_query_list'] == hash_query_list:
                    #         for tmp_key in tmp_dict.keys():
                    #             if tmp_dict[tmp_key]['hash_query_list'] == hash_query_list and tmp_dict[tmp_key]['fingerprint'] == final_dict[key]['fingerprint']:
                    #                 for v in tmp_dict[tmp_key]['values']:
                    #                     final_dict[key]['values'][v].update(tmp_dict[tmp_key]['values'][v])
                    #     elapsed_time = time.process_time() - t
                    #
                    #     print(f"{len(tmp_dict)} - {elapsed_time}")

                    del tmp_dict[tmp_hash_trx]

                ## merge all trx to final here

        #print(f"!!!!!!! {final_dict}")



        finger.save_dict(final_dict)
        # data=json.dumps(finger.get_dic(), cls=SetEncoder)
        # #j = dumps(finger.get_dic(), cls=PythonObjectEncoder)
        # #finger.write_dict()
        # with open("pyload_query_dictionary.json", "w") as json_file:
        #     json.dump(data, json_file)
        # #print(finger.get_dic())

        # for row in b:
        #    if line_count != 0:
        #        finger.createFingerprint(row['query'])
        #        line_count +=1
        # readC.parseSlowLog(slowlogFile)
        # readC.cleanDB()
        # data={"q1": {'id': 'John Smith', 'name': 'Accounting', 'count': 'November'},
        # "q2":{'id': 'BJohn Smith', 'name': 'Accounting', 'count': 'November'}}


if __name__ == "__main__":

    readC = readData()
    finger = fingerprint()

    main(sys.argv[1:])
