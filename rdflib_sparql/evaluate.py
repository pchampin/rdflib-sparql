from rdflib import Variable, URIRef, Literal, Graph

from rdflib_sparql.parserutils import CompValue
from rdflib_sparql.operators import simplify, EBV
from rdflib_sparql.sparql import QueryContext, NotBoundError, AlreadyBound, SPARQLError

from algebra import findFiltersQuery


def triples(l): 
    if (len(l) % 3) != 0: 
        import pdb ; pdb.set_trace()
        raise Exception('these aint triples')
    return [(l[x],l[x+1],l[x+2]) for x in range(0,len(l),3)]

def matchBGP(bgp, ctx): 
    
    if not bgp:
        yield ctx
        return 
    
    s,p,o=[ctx.absolutize(x) for x in bgp[0]]

    #import nose.tools ;nose.tools.set_trace()
    

    _s=ctx[s]
    _p=ctx[p]
    _o=ctx[o]

    for ss,sp,so in ctx.graph.triples((_s,_p,_o)):
        try: 
            if not all((_s,_p,_o)): 
                ctx.push()

            if _s==None: ctx[s]=ss

            try: 
                if _p==None: ctx[p]=sp
            except AlreadyBound: 
                continue

            try: 
                if _o==None: ctx[o]=so
            except AlreadyBound: 
                continue

            for _ctx in matchBGP(bgp[1:],ctx): 
                yield _ctx

        finally:
            if not all((_s,_p,_o)): 
                ctx.pop()



def evalGroupOrUnionGraphPattern(ctx,pattern):
    # pattern.graph is a list of GroupGraphPatterns to union
    pass

def evalGroupGraphPatternSub(ctx, pattern):
    pass
    



def evalQuery(graph, query, initBindings, initNs):
    ctx=QueryContext(graph)

    if initBindings:
        for k,v in initBindings.iteritems(): 
            if not isinstance(k, Variable):
                k=Variable(k)
            ctx[k]=v
        ctx.push() # nescessary?

    if initNs:
        for k,v in initNs:
            ctx.namespace_manager.bind(k,v)

    prologue=query[0]
    for x in prologue:
        if x.name=='Base': 
            ctx.base=x.iri
        elif x.name=='PrefixDecl':
            ctx.namespace_manager.bind(x.prefix, ctx.absolutize(x.iri))
            
    
    # valuesClause = query[2]

    main=query[1]

    if isinstance(main, CompValue):

        if main.name=='SelectQuery': 
            return evalSelectQuery(ctx,main)
        elif main.name=='AskQuery':
            return evalAskQuery(ctx,main)
        elif main.name=='ConstructQuery':
            return evalConstructQuery(ctx,main)
        elif main.name=='DescribeQuery':
            raise Exception('DESCRIBE not implemented')
        else: 
            raise Exception('I do not know this type of query: %s'%main.name)

    raise Exception('Urk!')

def evalPart(ctx, part):
    if part.name=='TriplesBlock':
        for c in matchBGP(triples(part.triples), ctx):
            yield c
    elif part.name=='Filter': 
        yield ctx # handled outside
    elif part.name=='OptionalGraphPattern':
        solutions=False
        for c in evalParts(ctx,part.graph.part):
            solutions=True
            yield c

        if not solutions: yield ctx # optional!            
    else: 
        #import pdb ; pdb.set_trace()
        raise Exception('I dont know: %s'%part.name)

def evalParts(ctx, parts):
    if not parts:
        yield ctx
        return

    for c in evalPart(ctx, parts[0]): 
        for s in evalParts(c, parts[1:]):
            yield s
    

def evalAskQuery(ctx, query):            

    #import pdb; pdb.set_trace()

    if query.limitoffset:
        raise Exception("As far as I know limit and offset make no sense for ASK queries.")

    filters=findFiltersQuery(query)
    filters=simplify(filters) # TODO move me!

    answer=False

    for c in evalParts(ctx, query.where.part):
        try: 
            if filters and not EBV(filters.eval(c)):
                print "Filter fail",c
                continue
        except NotBoundError:
            print "Filter NotBound fail",c
            continue
        answer=True
        break
        
    res={}
    res["type_"]="ASK"    
    res["askAnswer"]=answer

    return res

def evalSelectQuery(ctx, query):

    #import pdb; pdb.set_trace()

    selectVars=None
    limit=None
    offset=0

    bindings=[]
    if query.limitoffset:
        if query.limitoffset.limit: 
            limit=query.limitoffset.limit.toPython()
        if query.limitoffset.offset:             
            offset=query.limitoffset.offset.toPython()

    if query.var: 
        selectVars=query.var

    distinct=query.modifier and query.modifier=='DISTINCT'
    distinctSet=set()

    filters=findFiltersQuery(query)
    print filters
    filters=simplify(filters) # TODO move me!
    print filters

    i=0
    for c in evalParts(ctx, query.where.part):
        try: 
            if filters and not EBV(filters.eval(c)):
                print "Filter fail",c
                continue
        except SPARQLError:
            print "Filter ERRROR fail",c
            continue
        except NotBoundError:
            print "Filter NotBound fail",c
            continue

        if i>=offset:
            solution=c.solution(selectVars)
            if distinct:                
                solutionTuple=tuple(sorted(solution.iteritems())) # dicts are not hashable
                if solutionTuple not in distinctSet:
                    bindings.append(solution)
                    distinctSet.add(solutionTuple)
            else: 
                bindings.append(solution)
        i+=1
        if limit!=None and i>=limit+offset: 
            break

    res={}
    res["type_"]="SELECT"

    
    res["bindings"]=bindings

    if selectVars:
        res["vars_"]=selectVars    
    else: 
        res["vars_"]=ctx.vars

    return res


def evalConstructQuery(ctx, query):

    #import pdb; pdb.set_trace()

    limit=None
    offset=0

    if query.limitoffset:
        if query.limitoffset.limit: 
            limit=query.limitoffset.limit.toPython()
        if query.limitoffset.offset:             
            offset=query.limitoffset.offset.toPython()


    filters=findFiltersQuery(query)
    print filters
    filters=simplify(filters) # TODO move me!
    print filters

    template=triples(query.template)

    graph=Graph()

    i=0
    for c in evalParts(ctx, query.where.part):
        try: 
            if filters and not EBV(filters.eval(c)):
                print "Filter fail",c
                continue
        except SPARQLError:
            print "Filter ERRROR fail",c
            continue
        except NotBoundError:
            print "Filter NotBound fail",c
            continue

        if i>=offset:

            for t in template:
                s,p,o=[c.absolutize(x) for x in t]

                _s=ctx[s]
                _p=ctx[p]
                _o=ctx[o]
                
                if not isinstance(_s, Variable) and \
                        not isinstance(_p, Variable) and \
                        not isinstance(_o, Variable):
                
                    graph.add((_s,_p,_o))

        i+=1
        if limit!=None and i>=limit+offset: 
            break

    res={}
    res["type_"]="CONSTRUCT"
    res["graph"]=graph
    

    return res