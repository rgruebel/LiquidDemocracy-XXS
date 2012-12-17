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
#[d for d in node.inV('personDelegation').next().outV('personDelegation') for i in d.outV('delegationParlament') if i in db.proposals.get(31).outV('proposalHasParlament')]
#list.sort(key=lambda r: r.datetime_created,reverse=True)
#node=db.people.get(17).outV("personDelegation").next()
#[i.title for d in node.inV('personDelegation').next().outV('personDelegation') for i in d.outV('delegationParlament')]

#delegationProposal -> priorltaet 1
#delegationParlament -> prioritaet 2
#nur delegationPerson -> prioritaet 3
def countVotingWeight(personID,proposalID):
  '''Zaehlt das Stimmgewicht der uebergebenen Person bei dem uerbegebenen Vorschlag.
    Die child_list enthaelt am schluss alle ids der gezaehlten Stimmen.
  '''
  db=Graph()
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
        elif not any(x.element_type=='proposal' for x in delegationDetail):
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
def affectedVotes():
  '''ueberprueft bei welchen Proposals das Voting neu berechent werden muss beim anlegen oder loeschen einer delegation.
  Beim erstellen:delegation erst erstellen dann Voting neu berechnen'''
  q=  '''START i=node({userid}) 
    MATCH i-[:personDelegation*]->x-[:delegationPerson|personDelegation|votes*] ->p 
    WHERE (p.element_type="proposal" or p.element_type="comment") RETURN distinct ID(p)
    '''
  return reduce(operator.add, db.cypher.table(q,dict(userid=session['userId']))[1])

def recalculateAffectedVotes(result):
  '''Berechnet die uebergebenden Proposals neu'''
  db=Graph()
  for p in result:
    q='''START i=node({proposalid}) MATCH p-[r:votes]->i RETURN ID(p) AS voterID,r.pro AS pro'''
    votes=db.cypher.table(q,dict(proposalid=p))[1]
    downs=0
    ups=0
    if db.proposals.get(p).element_type == 'comment':
      countId=db.proposals.get(p).inV('hasComment').next().eid
    else:
      countId=p
    for v in votes:
      if v[1]==1:
        ups+=len(countVotingWeight(v[0],countId))
      elif v[1]==0:
        downs+=len(countVotingWeight(v[0],countId))
    c_p=db.vertices.get(p)
    c_p.ups=ups
    c_p.downs=downs
    c_p.save() 
  return result
def countVotingWeightOld(generator,votes,prop,result):
	'''Rekursiver ansatz der obigen Funktion, verworfen wegen bedenken der Rekusrionstiefe'''
	for i in generator:
		if i.element_type == 'delegation':
			for x in i.outV():
				if x.eid==prop.eid and x.element_type=='proposal':
					countVotingWeightOld(i.inV('personDelegation'),votes,prop,result)		
				elif x.element_type=='parlament':
					countVotingWeightOld(i.inV('personDelegation'),votes,prop,result)
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

#votes=[p.eid for p in db.proposals.get(20).inV('votes')]
q='START i=node({userid}) MATCH i-[:personDelegation]->d-[:delegationParlament|delegationProposal]->p RETURN ID(p),p.element_type,ID(d)'
result=db.cypher.table(q,dict(userid=1))[1]
any(p[0]==44 and p[1] == 'parlament' for p in result)

#voting= countVotingWeight(25,52)
#print voting
#print 'Stimmgewicht ='+str(len(voting))
#print recalculateAffectedVotes()
#for x in db.delegations.get_all():
#	db.client.delete_vertex(x.eid)
def getDelegations(instanceID):
  for person in db.instances.get(instanceID).outV('hasPeople'):
    for delegation in person.outV('personDelegation'):
      print person.username +' delegiert '+delegation.outV('delegationPerson').next().username+' fuer ' +delegation.delegation_type 


