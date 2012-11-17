from flask import Flask, session, render_template, request, redirect, url_for, escape, flash, g, abort, jsonify
from model import Graph
from datetime import datetime
from utils import date_diff
from collections import deque
import re
import operator

# configuration
DATABASE = 'graphdatabase'
DEBUG = True
SECRET_KEY = 'blubber'
USERNAME = 'tobias'
PASSWORD = 'bla'


db = Graph()


def recalculateAffectedVotes():
	'''ueberprueft bei welchen Proposals das Voting neu berechent werden muss beim anlegen oder loeschen einer delegation.
	Beim erstellen:delegation erst erstellen dann Voting neu berechnen'''
	q= 	'''START i=node({userid}) 
		MATCH i-[:personDelegation*]->x-[:delegationPerson|personDelegation|votes*] ->p 
		WHERE (p.element_type="proposal") RETURN distinct ID(p)
		'''
	#result = db.cypher.table(q,dict(userid=session['userId']))[1]
	result = reduce(operator.add, db.cypher.table(q,dict(userid=7))[1])
	#TODO:In in schleife Voting aktualisieren
	return result
#delegationProposal -> priorltaet 1
#delegationParlament -> prioritaet 2
#nur delegationPerson -> prioritaet 3
def countVotingWeight(personID,proposalID):
	'''Zaehlt das Stimmgewicht der uebergebenen Person bei dem uerbegebenen Vorschlag.
		Die child_list enthaelt am schluss alle ids der gezaehlten Stimmen.
	'''
	#Liste welche die eid jeder gueltigen Person(Stimme) enthaelt
	child_list=[personID]
	#Alle eids welche beim uebergebenen proposalID bereits selbst gevotet haben(pfad der delegation endet dann)
	votes=[p.eid for p in db.proposals.get(proposalID).inV('votes')]
	#Stack der zu zu durchlaufenden nodes, wird erweitert in der Schleife
	to_crawl=deque(list(db.vertices.get(personID).inV("delegationPerson")))
	while to_crawl:
		node = to_crawl.popleft()
		if node.element_type=='delegation':
			delegationDetail = list(node.outV())
			#Wenn delegation zu einem Proposal zeigt und dieses auch noch passende Id hat.
			#In meiner ueberlegung die hoechste Prioritaet.
			if any(x.element_type=='proposal' and x.eid ==proposalID for x in delegationDetail):
				to_crawl.extend(list(node.inV('personDelegation')))
			#Hat ein andere User eine delegation bekommen welche direkt zum Proposal geht?
			elif not any(i.eid==proposalID for d in node.inV('personDelegation').next().outV('personDelegation') for i in d.outV('delegationProposal')):
				#Handelt es sich um eine Delegation fuer ein Parlament?
				if any(x.element_type=='parlament' for x in delegationDetail):
					#Hat das Proposal mehrere Delegationen vom Benutzer?Dann gilt die zuletzt angelegte.
					parlaments=[(p.eid,p.datetime_created) for p in db.proposals.get(proposalID).outV('proposalHasParlament')]
					parlaments.sort(key=lambda r: r[1],reverse=True)
					if not parlaments==[] and node.outV('delegationParlament').next().eid == parlaments[0][0]:
						to_crawl.extend(list(node.inV('personDelegation')))			
				else:
					to_crawl.extend(list(node.inV('personDelegation')))
		elif node.element_type=='person':
			#Wenn Person selbst gevotet hat Pfad unterbrechen, ansonsten stimme zaehlen und weiter maschieren
			if not node.eid in votes:
				if not node.eid in child_list:
					child_list.append(node.eid)
					to_crawl.extend(list(node.inV('delegationPerson')))
			else:
				pass #User hat bereits gevotet
	return child_list

def countVotingWeightOld(generator,votes,prop,result):
	'''Rekursiver ansatz der obigen Funktion, verworfen wegen bedenken der Rekusrionstiefe'''
	#any(x.element_type=='parlaments' for x in bla[0].outV())
	#[i.eid for x in db.people.get(1).outV('personDelegation') for i in x.outV('delegationProposal')]
	for i in generator:
		#Pruefen ob delegation bei aktuellem Proposal gueltig ist
		if i.element_type == 'delegation':
			for x in i.outV():
				#Wenn delegation auf aktuellen Vorschlag zeigt(hoechste Prioritaet)
				if x.eid==prop.eid and x.element_type=='proposal':
					countVotingWeightOld(i.inV('personDelegation'),votes,prop,result)
				#Delegation zeigt zu einem Parlament
				elif x.element_type=='parlament':
					#Wenn der User der die delegation erstellt hat keine andere delegation hat welche direkt zum Vorschlag gehen:
					#if not any(i.eid==prop.eid for x in i.inV('personDelegation').next().outV('personDelegation') for i in x.outV('delegationProposal')):
					countVotingWeightOld(i.inV('personDelegation'),votes,prop,result)
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
				countVotingWeightOld(i.inV("delegationPerson"),votes,prop,result)						
	return result

def work():
	test=countVotingWeight(db.vertices.get(25).inV("delegationPerson"),[p.eid for p in db.proposals.get(20).inV('votes')],db.proposals.get(20),[])
	if test == []:
		print "keine Delegationen"
	else:
		print test
#work()
voting= countVotingWeight(25,52)
print voting
print 'Stimmgewicht ='+str(len(voting))
#print recalculateAffectedVotes()