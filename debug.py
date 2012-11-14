from flask import Flask, session, render_template, request, redirect, url_for, escape, flash, g, abort, jsonify
from model import Graph
from datetime import datetime
from utils import date_diff
from collections import deque
import re

# configuration
DATABASE = 'graphdatabase'
DEBUG = True
SECRET_KEY = 'blubber'
USERNAME = 'tobias'
PASSWORD = 'bla'


db = Graph()
#delegationProposal -> priorltaet 1
#delegationParlament -> prioritaet 2
#nur delegationPerson -> prioritaet 3
def countVotingWeightNew(personID,proposalID):
	'''Zaehlt das Stimmgewicht der uebergebenen Person bei dem uerbegebenen Vorschlag.
		Die child_list enthaelt am schluss alle ids der gezaehlten Stimmen.
	'''
	child_list=[]
	votes=[p.eid for p in db.proposals.get(proposalID).inV('votes')]
	to_crawl=deque(list(db.vertices.get(personID).inV("delegationPerson")))
	while to_crawl:
		node = to_crawl.popleft()
		if node.element_type=='delegation':
			delegationDetail = list(node.outV())
			if any(x.element_type=='proposal' and x.eid ==proposalID for x in delegationDetail):
				to_crawl.extend(list(node.inV('personDelegation')))
			elif not any(i.eid==proposalID for d in node.inV('personDelegation').next().outV('personDelegation') for i in d.outV('delegationProposal')):
				if any(x.element_type=='parlament' for x in delegationDetail):
					parlaments=[(p.eid,p.datetime_created) for p in db.proposals.get(proposalID).outV('proposalHasParlament')]
					parlaments.sort(key=lambda r: r[1],reverse=True)
					if not parlaments==[] and node.outV('delegationParlament').next().eid == parlaments[0][0]:
						to_crawl.extend(list(node.inV('personDelegation')))
					print parlaments	
					print node.outV('delegationParlament').next().eid				
				else:
					print 'delegation fuer alles'
		elif node.element_type=='person':
			if not node.eid in votes:
				print node.username +' hat nicht gevotet'
				child_list.append(node.eid)
				to_crawl.extend(list(node.inV('delegationPerson')))
			else:
				print node.username +' hat bereits gevotet'
			print node.eid
	return child_list

def countVotingWeight(generator,votes,prop,result):
	'''Rekursiver ansatz der obigen Funktion, verworfen wegen bedenken der Rekusrionstiefe'''
	#any(x.element_type=='parlaments' for x in bla[0].outV())
	#[i.eid for x in db.people.get(1).outV('personDelegation') for i in x.outV('delegationProposal')]
	for i in generator:
		#Pruefen ob delegation bei aktuellem Proposal gueltig ist
		if i.element_type == 'delegation':
			for x in i.outV():
				#Wenn delegation auf aktuellen Vorschlag zeigt(hoechste Prioritaet)
				if x.eid==prop.eid and x.element_type=='proposal':
					countVotingWeight(i.inV('personDelegation'),votes,prop,result)
				#Delegation zeigt zu einem Parlament
				elif x.element_type=='parlament':
					#Wenn der User der die delegation erstellt hat keine andere delegation hat welche direkt zum Vorschlag gehen:
					#if not any(i.eid==prop.eid for x in i.inV('personDelegation').next().outV('personDelegation') for i in x.outV('delegationProposal')):
					countVotingWeight(i.inV('personDelegation'),votes,prop,result)
						#print [p.title for p in prop.outV('proposalHasParlament')]
						#print 'hallo'
						#print list(x.inV())
						#print i.inV('personDelegation').next().username
		#Pruefen ob der User bereits selbst gevotet hat
		elif i.element_type=='person':
			print i.eid			
			if i.eid in votes:
				print i.username +' hat gevotet'
			else:
				print i.username +' hat nicht gevotet'
				result.append(i.eid)
				countVotingWeight(i.inV("delegationPerson"),votes,prop,result)						
	return result

def work():
	test=countVotingWeight(db.vertices.get(25).inV("delegationPerson"),[p.eid for p in db.proposals.get(20).inV('votes')],db.proposals.get(20),[])
	if test == []:
		print "keine Delegationen"
	else:
		print test
#work()
print countVotingWeightNew(25,5)
