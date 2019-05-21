# -*- coding: utf-8 -*-
import numpy as np
import xml.etree.ElementTree as ET
import os, fnmatch
import argparse
import time
import json
import spacy


def str2bool(v):
    if v.lower() in ('yes', 'true', 't', 'y', '1'):
        return True
    elif v.lower() in ('no', 'false', 'f', 'n', '0'):
        return False
    else:
        raise argparse.ArgumentTypeError('Boolean value expected.')




VALIDATION = ['2', '5', '12', '18', '21', '23', '34', '35']
TRAIN = [str(i) for i in range(1, 36) if str(i) not in VALIDATION]
TEST = [str(i) for i in range(36, 46)]


parser = argparse.ArgumentParser(description='Parsing ECB+ corpus')

parser.add_argument('--download_data', type=int, default=0, help='To donwload the data and unzip')

parser.add_argument('--data_path', type=str, default='datasets/ECB+_LREC2014/ECB+',
                    help=' Path to ECB+ corpus')

parser.add_argument('--output_dir', type=str, default='ecb_data',
                        help=' The directory of the output files')

parser.add_argument('--cybulska_setup', type=str, default='datasets/ECB+_LREC2014/ECBplus_coreference_sentences.csv',
                    help='The path to a file contains selected sentences from the ECB+ corpus according to Cybulska')

parser.add_argument('--use_setup', type=str2bool, default=True)

parser.add_argument('--with_pos', type=str2bool, default=False, help='Boolean value to include the pos tag of the mentions')

args = parser.parse_args()

if args.with_pos:
    print('Using spacy...')
    nlp = spacy.load('en_core_web_sm')


def get_list_annotated_sentences(annotated_sentences):
    sentences = {}
    for topic, doc, sentence in annotated_sentences:
        if topic not in sentences:
            sentences[topic] = {}
        if doc not in sentences[topic]:
            sentences[topic][doc] = []
        sentences[topic][doc].append(sentence)
    return sentences


def obj_dict(obj):
    return obj.__dict__


def get_all_mention(corpus_path, output_dir, sentences_setup=None):
    train_events = []
    train_entities = []
    dev_events = []
    dev_entities = []
    test_events = []
    test_entities = []
    vocab = set()

    train_sentences = []
    dev_sentences = []
    test_sentences = []

    for folder in os.listdir(corpus_path):
        folder_path = corpus_path + '/' + folder
        if os.path.isdir(folder_path):
            if args.use_setup:
                event_mentions, entity_mentions, files, voc = get_topic_mention(folder_path, sentences_setup[folder])
            else:
                event_mentions, entity_mentions, files, voc = get_topic_mention(folder_path)
            vocab.update(voc)
            if folder in TRAIN:
                train_events.extend(event_mentions)
                train_entities.extend(entity_mentions)
                train_sentences.extend(files)
            elif folder in VALIDATION:
                dev_events.extend(event_mentions)
                dev_entities.extend(entity_mentions)
                dev_sentences.extend(files)
            elif folder in TEST:
                test_events.extend(event_mentions)
                test_entities.extend(entity_mentions)
                test_sentences.extend(files)

    all_events = train_events + dev_events + test_events
    all_entities = train_entities + dev_entities + test_entities

    save_json(train_events, output_dir + '/train_event_gold_mentions.json')
    save_json(dev_events, output_dir + '/dev_event_gold_mentions.json')
    save_json(test_events, output_dir + '/test_event_gold_mentions.json')
    save_json(train_entities, output_dir + '/train_entity_gold_mentions.json')
    save_json(dev_entities, output_dir + '/dev_entity_gold_mentions.json')
    save_json(test_entities, output_dir + '/test_entity_gold_mentions.json')
    save_json(all_events, output_dir + '/all_event_gold_mentions.json')
    save_json(all_entities, output_dir + '/all_entity_gold_mentions.json')

    save_txt(train_sentences, output_dir + '/train_text.txt')
    save_txt(dev_sentences, output_dir + '/dev_text.txt')
    save_txt(test_sentences, output_dir + '/test_text.txt')


    with open(output_dir + '/vocab', 'w') as f:
        for word in vocab:
            f.write(word + '\n')

    return (train_events, train_entities), \
           (dev_events, dev_entities), \
           (test_events, test_entities), \
           (all_events, all_entities), \
           vocab



def save_json(dic, file_name):
    with open(file_name, 'w') as f:
        json.dump(dic, f, default=obj_dict, indent=4, sort_keys=True)


def save_txt(data, file_name):
    with open(file_name, 'w') as f:
        for item in data:
            f.write("%s\n" % '\t'.join(item))


def get_topic_mention(topic_path, sentences_setup=None):
    event_mentions = []
    entity_mentions = []
    pattern = '*.xml'
    vocab = set()
    files = []

    for file in os.listdir(topic_path):
        file_for_csv = file.split('_')[-1].split('.')[-2]
        if fnmatch.fnmatch(file, pattern) and (not args.use_setup or file_for_csv in sentences_setup):
            file_path = topic_path + '/' + file
            tree = ET.parse(file_path)
            root = tree.getroot()

            if args.use_setup:
                dic_sentences, voc = get_sentences_of_file(root, sentences_setup[file_for_csv])
                events, entities = get_file_mention(root, file, dic_sentences, sentences_setup[file_for_csv])
            else:
                dic_sentences, voc = get_sentences_of_file(root)
                events, entities = get_file_mention(root, file, dic_sentences)

            files.extend(get_tokens_from_file(root, file))
            event_mentions.extend(events)
            entity_mentions.extend(entities)
            vocab.update(voc)

    return event_mentions, entity_mentions, files, vocab



def get_tokens_from_file(root, file_name):
    tokens = []

    sentence = 0
    for token in root:
        if token.tag == 'token':
            if int(token.attrib['sentence']) > sentence:
                tokens.append([])
                sentence += 1
            tokens.append([file_name, token.attrib['sentence'], token.attrib['number'], token.text])

    tokens.append([])
    return tokens


def get_file_mention(root, file_name, sentences_text, sentences_setup=None):
    event_mentions = []
    entity_mentions = []

    topic, sub = file_name.split('_')[0], file_name[-3:]
    if sub == 'ecb':
        subtopic = topic + 'ecb'
    else:
        subtopic = topic + 'ecb+'

    mentions_dic = {}
    relation_mention_dic = {}

    for mention in root.find('Markables'):
        if mention.attrib.get('RELATED_TO', None) is None:
            m_id = mention.attrib['m_id']
            t_ids = []
            for term in mention:
                t_ids.append(term.attrib['t_id'])
            terms_ids = list(map(lambda x: int(x) - 1, t_ids))
            sentence = root[int(terms_ids[0])].attrib['sentence']

            if args.use_setup and sentence not in sentences_setup:
                continue

            term = ' '.join(list(map(lambda x: root[x].text, terms_ids)))
            if mention.tag.startswith('ACT') or mention.tag.startswith('NEG'):
                mention_type = 'event'
            else:
                mention_type = 'entity'

            sentence_desc = ' '.join(x[1] for x in sentences_text[sentence])
            left = ' '.join(word for token_id, word in sentences_text[sentence] if int(token_id) < int(t_ids[0]))
            right = ' '.join(word for token_id, word in sentences_text[sentence] if int(token_id) > int(t_ids[-1]))

            is_pronoun = False
            tags = []
            if args.with_pos:
                doc = nlp(term)

                for token in doc:
                    tags.append(token.tag_)

                if len(tags) == 1 and (tags[0] == 'PRP' or tags[0] == 'PRPS'):
                    is_pronoun = True


            mentions_dic[m_id] = {
                    'doc_id': file_name,
                     'topic': topic,
                     'subtopic': subtopic,
                     'sent_id':sentence,
                     'm_id': m_id,
                     'tokens_ids': terms_ids,
                     'mention_type': mention.tag[:3],
                     'tokens_str': term,
                     'tags': tags,
                     'event_entity': mention_type,
                     'full_sentence': sentence_desc,
                     'left_sentence': left,
                     'right_sentence': right,
                     'is_pronoun': is_pronoun
                     }

        else:
            m_id = mention.attrib['m_id']
            relation_mention_dic[m_id] = {
                'coref_chain': mention.attrib.get('instance_id', ''),
                'cluster_desc': mention.attrib['TAG_DESCRIPTOR']
            }

    relation_source_target = {}
    relation_rid = {}
    relation_tag = {}


    for relation in root.find('Relations'):
        target_mention = relation[-1].attrib['m_id']
        relation_tag[target_mention] = relation.tag
        relation_rid[target_mention] = relation.attrib['r_id']
        for mention in relation:
            if mention.tag == 'source':
                relation_source_target[mention.attrib['m_id']] = target_mention


    for mention, dic in mentions_dic.items():
        target = relation_source_target.get(mention, None)
        desc_cluster = ''
        if target is None:
            id_cluster = 'Singleton_' + dic['mention_type'] + '_' + dic['m_id'] + '_' +  dic['doc_id']
        else:
            r_id = relation_rid[target]
            tag = relation_tag[target]

            if tag.startswith('INTRA'):
                id_cluster = 'INTRA_' + r_id + '_' + dic['doc_id']
            else:
                id_cluster = relation_mention_dic[target]['coref_chain']

            desc_cluster = relation_mention_dic[target]['cluster_desc']


        mention_obj = dic.copy()
        mention_obj['coref_chain'] = id_cluster
        mention_obj['cluster_desc'] = desc_cluster

        if mention_obj['event_entity'] == 'event':
            event_mentions.append(mention_obj)
        else:
            entity_mentions.append(mention_obj)

    return event_mentions, entity_mentions



def get_sentences_of_file(root, sentences=None):
    dict = {}
    vocab = set()

    sentence = []
    i = 0
    for child in root:
        sentence_num = child.attrib.get('sentence')
        if sentence_num == str(i):
            sentence.append([child.attrib.get('t_id'), child.text])
            vocab.add(child.text)
        else:
            if len(sentence) > 0 and (args.use_setup is False or str(i) in sentences):
                dict[str(i)] = sentence
            sentence = []
            if child.attrib.get('t_id') is not None:
                sentence.append([child.attrib.get('t_id'), child.text])
                vocab.add(child.text)
                i += 1

    return dict, vocab




def get_all_chains(mentions):
    chains = {}
    for mention_dic in mentions:
        chain_id = mention_dic['coref_chain']
        chains[chain_id] = [] if chain_id not in chains else chains[chain_id]
        chains[chain_id].append(mention_dic)

    return chains




def get_statistics(data_events, data_entities, data_desc, stat_file):
    topics = set()
    docs = set()
    subtopics = set()
    sentences = set()
    entities = 0
    events = 0
    human = 0
    non_human = 0
    loc = 0
    tim = 0
    event_mentions_with_multiple_tokens = 0
    entity_mentions_with_multiple_tokens = 0

    for mention_dic in data_entities:
        topics.add(mention_dic["topic"])
        docs.add(mention_dic["doc_id"])
        subtopics.add(mention_dic["subtopic"])
        sentences.add(mention_dic["doc_id"] + '_' + mention_dic["sent_id"])
        entities += 1
        if len(mention_dic['tokens_ids']) > 1:
            entity_mentions_with_multiple_tokens += 1

        tag = mention_dic['mention_type']
        if tag == 'HUM':
            human += 1
        elif tag == 'NON':
            non_human += 1
        elif tag == 'LOC':
            loc += 1
        elif tag == 'TIM':
            tim += 1

    for mention_dic in data_events:
        topics.add(mention_dic["topic"])
        docs.add(mention_dic["doc_id"])
        subtopics.add(mention_dic["subtopic"])
        sentences.add(mention_dic["doc_id"] + '_' + mention_dic["sent_id"])
        events += 1
        if len(mention_dic['tokens_ids']) > 1:
            event_mentions_with_multiple_tokens += 1



    event_chains = get_all_chains(data_events)
    entity_chains = get_all_chains(data_entities)
    event_singleton = len({id_cluster:mention for id_cluster, mention in event_chains.items() if len(mention) == 1})
    entity_singleton = len({id_cluster:mention for id_cluster, mention in entity_chains.items() if len(mention) == 1 })


    stat_file.write('\n')
    stat_file.write('Statistics on the {} set\n'.format(data_desc))
    stat_file.write('Topics: {}\n'.format(len(topics)))
    stat_file.write('Subtopics: {}\n'.format(len(subtopics)))
    stat_file.write('Docs: {}\n'.format(len(docs)))
    stat_file.write('Sentences: {}\n'.format(len(sentences)))
    stat_file.write('Event mentions: {}\n'.format(events))
    stat_file.write('Entity mentions: {}\n'.format(entities))
    stat_file.write('Event mentions with more than one token: {}\n'.format(event_mentions_with_multiple_tokens))
    stat_file.write('Entity mentions with more than one token: {}\n'.format(entity_mentions_with_multiple_tokens))
    stat_file.write('Human entity mentions: {}\n'.format(human))
    stat_file.write('Non Human entity mentions: {}\n'.format(non_human))
    stat_file.write('Location entity mentions: {}\n'.format(loc))
    stat_file.write('Time entity mentions: {}\n'.format(tim))
    stat_file.write('Event chains: {}\n'.format(len(event_chains)))
    stat_file.write('Event Singleton: {}\n'.format(event_singleton))
    stat_file.write('Entity chains: {}\n'.format(len(entity_chains)))
    stat_file.write('Entity Singleton: {}\n'.format(entity_singleton))
    stat_file.write('--------------------------------------\n')



def download_data():
    print('Downloading ECB+ data...')
    url = 'kyoto.let.vu.nl/repo/ECB+_LREC2014.zip'
    os.system('wget %s' % url)
    os.system('unzip %s' % 'ECB+_LREC2014.zip')
    os.system('rm %s' % 'ECB+_LREC2014.zip')
    os.chdir('ECB+_LREC2014')
    os.system('unzip %s' % 'ECB+.zip')
    os.system('rm %s' % 'ECB+.zip')
    os.chdir('..')





if __name__ == '__main__':
    start = time.time()

    if args.download_data == 1:
        download_data()

    annotated_sentences = None
    if args.use_setup:
        annotated_sentences = np.genfromtxt(args.cybulska_setup, delimiter=',', dtype=np.str, skip_header=1)
        annotated_sentences = get_list_annotated_sentences(annotated_sentences)


    if not os.path.exists(args.output_dir):
        os.makedirs(args.output_dir)

    print('Getting all mentions')
    train, dev, test, all, vocab = get_all_mention(args.data_path, args.output_dir, annotated_sentences)

    print('Getting mention statistics')
    stat_file = open(args.output_dir + '/statistics', 'w')
    get_statistics(train[0], train[1], 'train', stat_file)
    get_statistics(dev[0], dev[1], 'dev', stat_file)
    get_statistics(test[0], test[1], 'test', stat_file)
    get_statistics(all[0], all[1], 'all', stat_file)
    stat_file.close()


    end = time.time() - start
    print('Time: {}'.format(end))