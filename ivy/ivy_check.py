#
# Copyright (c) Microsoft Corporation. All Rights Reserved.
#
import ivy_init
import ivy_interp as itp
import ivy_actions as act
import ivy_utils as utl
import ivy_logic_utils as lut
import ivy_logic as lg
import ivy_utils as iu
import ivy_module as im
import ivy_alpha
import ivy_art
import ivy_interp
import ivy_compiler
import ivy_isolate
import ivy_ast
import ivy_theory as ith
import ivy_transrel as itr

import sys
from collections import defaultdict

diagnose = iu.BooleanParameter("diagnose",False)
coverage = iu.BooleanParameter("coverage",True)
checked_action = iu.Parameter("action","")
opt_trusted = iu.BooleanParameter("trusted",False)

def display_cex(msg,ag):
    if diagnose.get():
        import tk_ui as ui
        iu.set_parameters({'mode':'induction'})
        ui.ui_main_loop(ag)
        exit(1)
    raise iu.IvyError(None,msg)
    
def check_properties():
    if itp.false_properties():
        if diagnose.get():
            print "Some properties failed."
            import tk_ui as ui
            iu.set_parameters({'mode':'induction'})
            gui = ui.new_ui()
            gui.tk.update_idletasks() # so that dialog is on top of main window
            gui.try_property()
            gui.mainloop()
            exit(1)
        raise iu.IvyError(None,"Some properties failed.")
    im.module.labeled_axioms.extend(im.module.labeled_props)
    im.module.update_theory()

def show_counterexample(ag,state,bmc_res):
    universe,path = bmc_res
    other_art = ivy_art.AnalysisGraph()
    ag.copy_path(state,other_art,None)
    for state,value in zip(other_art.states[-len(path):],path):
        state.value = value
        state.universe = universe

    import tk_ui as ui
    iu.set_parameters({'mode':'induction'})
    gui = ui.new_ui()
    agui = gui.add(other_art)
    gui.tk.update_idletasks() # so that dialog is on top of main window
    gui.tk.mainloop()
    exit(1)

    
def check_conjectures(kind,msg,ag,state):
    failed = itp.undecided_conjectures(state)
    if failed:
        if diagnose.get():
            print "{} failed.".format(kind)
            import tk_ui as ui
            iu.set_parameters({'mode':'induction'})
            gui = ui.new_ui()
            agui = gui.add(ag)
            gui.tk.update_idletasks() # so that dialog is on top of main window
            agui.try_conjecture(state,msg="{}\nChoose one to see counterexample.".format(msg),bound=1)
            gui.tk.mainloop()
            exit(1)
        raise iu.IvyError(None,"{} failed.".format(kind))

def has_temporal_stuff(f):
    return any(True for x in lut.temporals_ast(f)) or any(True for x in lut.named_binders_ast(f))

    
def check_temporals():
    props = im.module.labeled_props
    proved = []
    for prop in props:
        if prop.temporal:
            from ivy_l2s import l2s
            mod = im.module.copy()
            mod.labeled_axioms.extend(proved)
            mod.labeled_props = []
            l2s(mod, prop)
            mod.concept_spaces = []
            mod.update_conjs()
            with mod:
                check_isolate()
        proved.append(prop)
    # filter out any temporal stuff from conjectures and concept spaces
    im.module.labeled_conjs = [x for x in im.module.labeled_conjs if not has_temporal_stuff(x.formula)]
    im.module.concept_spaces = [x for x in im.module.concept_spaces if not has_temporal_stuff(x[1])]


def usage():
    print "usage: \n  {} file.ivy".format(sys.argv[0])
    sys.exit(1)

def find_assertions(action_name=None):
    res = []
    actions = act.call_set(action_name,im.module.actions) if action_name else im.module.actions.keys()
    for actname in actions:
        action = im.module.actions[actname]
        for a in action.iter_subactions():
            if isinstance(a,act.AssertAction) or isinstance(a,act.Ranking):
                res.append(a)
    return res

def show_assertions():
    for a in find_assertions():
        print '{}: {}'.format(a.lineno,a)

def get_checked_actions():
    cact = checked_action.get()
    if cact and 'ext:'+cact in im.module.public_actions:
        cact = 'ext:'+cact
    if cact and cact not in im.module.public_actions:
        raise iu.IvyError(None,'{} is not an exported action'.format(cact))
    return [cact] if cact else sorted(im.module.public_actions)

failures = 0

def print_dots():
    print '...',
    sys.stdout.flush()
    

class Checker(object):
    def __init__(self,conj,report_pass=True):
        self.fc = lut.dual_clauses(lut.formula_to_clauses(conj))
        self.report_pass = report_pass
    def cond(self):
        return self.fc
    def start(self):
        if self.report_pass:
            print_dots()
    def sat(self):
        print('FAIL')
        global failures
        failures += 1
        return not diagnose.get() # ignore failures if not diagnosing
    def unsat(self):
        if self.report_pass:
            print('PASS')
    def assume(self):
        return False

def pretty_label(label):
    return "(no name)" if label is None else label

def pretty_lineno(ast):
    return str(ast.lineno) if hasattr(ast,'lineno') else '(internal) '

def pretty_lf(lf,indent=8):
    return indent*' ' + "{}{}".format(pretty_lineno(lf),pretty_label(lf.label))
    
class ConjChecker(Checker):
    def __init__(self,lf,indent=8):
        self.lf = lf
        self.indent = indent
        Checker.__init__(self,lf.formula)
    def start(self):
        print pretty_lf(self.lf,self.indent),
        print_dots()
    
class ConjAssumer(Checker):
    def __init__(self,lf):
        self.lf = lf
        Checker.__init__(self,lf.formula)
    def start(self):
        print pretty_lf(self.lf) + "  [proved by tactic]"
    def assume(self):
        return True

def check_fcs_in_state(mod,ag,post,fcs):
    history = ag.get_history(post)
    gmc = lambda cls, final_cond: itr.small_model_clauses(cls,final_cond,shrink=diagnose.get())
    axioms = im.module.background_theory()
    res = history.satisfy(axioms,gmc,fcs)
    if res is not None and diagnose.get():
        show_counterexample(ag,post,res)
    return res is None

def check_conjs_in_state(mod,ag,post,indent=8):
    return check_fcs_in_state(mod,ag,post,[ConjChecker(c,indent) for c in mod.labeled_conjs])

def check_safety_in_state(mod,ag,post,report_pass=True):
    return check_fcs_in_state(mod,ag,post,[Checker(lg.Or(),report_pass=report_pass)])

def summarize_isolate(mod,check=True):

    subgoalmap = dict((x.id,y) for x,y in im.module.subgoals)
    axioms = [m for m in mod.labeled_axioms if m.id not in subgoalmap]
    schema_instances = [m for m in mod.labeled_axioms if m.id in subgoalmap]
    if axioms:
        print "\n    The following properties are assumed as axioms:"
        for lf in axioms:
            print pretty_lf(lf)

    if mod.definitions:
        print "\n    The following definitions are used:"
        for lf in mod.definitions:
            print pretty_lf(lf)

    if mod.labeled_props or schema_instances:
        print "\n    The following properties are to be checked:"
        if check:
            for lf in schema_instances:
                print pretty_lf(lf) + " [proved by axiom schema]"
            ag = ivy_art.AnalysisGraph()
            pre = itp.State()
            props = [x for x in im.module.labeled_props if not x.temporal]
            fcs = ([(ConjAssumer if prop.id in subgoalmap else ConjChecker)(prop) for prop in props])
            check_fcs_in_state(mod,ag,pre,fcs)
        else:
            for lf in schema_instances + mod.labeled_props:
                print pretty_lf(lf)

    # after checking properties, make them axioms
    im.module.labeled_axioms.extend(im.module.labeled_props)
    im.module.update_theory()


    if mod.labeled_inits:
        print "\n    The following properties are assumed initially:"
        for lf in mod.labeled_inits:
            print pretty_lf(lf)
    if mod.labeled_conjs:
        print "\n    The inductive invariant consists of the following conjectures:"
        for lf in mod.labeled_conjs:
            print "        {}{}".format(lf.lineno,"(no name)" if lf.label is None else lf.label)


    if mod.actions:
        print "\n    The following actions are present:"
        for actname,action in sorted(mod.actions.iteritems()):
            print "        {}{}".format(action.lineno,actname)

    if mod.initializers:
        print "\n    The following initializers are present:"
        for actname,action in sorted(mod.initializers, key=lambda x: x[0]):
            print "        {}{}".format(pretty_lineno(action),actname)

    if mod.labeled_conjs:
        print "\n    Initialization must establish the invariant"
        if check:
            with itp.EvalContext(check=False):
                ag = ivy_art.AnalysisGraph(initializer=lambda x:None)
                check_conjs_in_state(mod,ag,ag.states[0])
        else:
            print ''

    if mod.initializers:
        print "\n    Any assertions in initializers must be checked",
        if check:
            ag = ivy_art.AnalysisGraph(initializer=lambda x:None)
            fail = itp.State(expr = itp.fail_expr(ag.states[0].expr))
            check_safety_in_state(mod,ag,fail)


    checked_actions = get_checked_actions()

    if checked_actions and mod.labeled_conjs:
        print "\n    The following set of external actions must preserve the invariant:"
        for actname in sorted(checked_actions):
            action = mod.actions[actname]
            print "        {}{}".format(action.lineno,actname)
            if check:
                ag = ivy_art.AnalysisGraph()
                pre = itp.State()
                pre.clauses = lut.and_clauses(*mod.conjs)
                with itp.EvalContext(check=False): # don't check safety
                    post = ag.execute(action, pre, None, actname)
                check_conjs_in_state(mod,ag,post,indent=12)
            else:
                print ''
            


    callgraph = defaultdict(list)
    for actname,action in mod.actions.iteritems():
        for called_name in action.iter_calls():
            callgraph[called_name].append(actname)

    some_assumps = False
    for actname,action in mod.actions.iteritems():
        assumptions = [sub for sub in action.iter_subactions()
                           if isinstance(sub,act.AssumeAction)]
        if assumptions:
            if not some_assumps:
                print "\n    The following program assertions are treated as assumptions:"
                some_assumps = True
            callers = callgraph[actname]
            if actname in mod.public_actions:
                callers.append("the environment")
            prettyname = actname[4:] if actname.startswith('ext:') else actname
            prettycallers = [c[4:] if c.startswith('ext:') else c for c in callers]
            print "        in action {} when called from {}:".format(prettyname,','.join(prettycallers))
            for sub in assumptions:
                print "            {}assumption".format(pretty_lineno(sub))

    tried = set()
    some_guarants = False
    for actname,action in mod.actions.iteritems():
        guarantees = [sub for sub in action.iter_subactions()
                          if isinstance(sub,(act.AssertAction,act.Ranking))]
        if guarantees:
            if not some_guarants:
                print "\n    The following program assertions are treated as guarantees:"
                some_guarants = True
            callers = callgraph[actname]
            if actname in mod.public_actions:
                callers.append("the environment")
            prettyname = actname[4:] if actname.startswith('ext:') else actname
            prettycallers = [c[4:] if c.startswith('ext:') else c for c in callers]
            print "        in action {} when called from {}:".format(prettyname,','.join(prettycallers))
            roots = set(iu.reachable([actname],lambda x: callgraph[x]))
            for sub in guarantees:
                print "            {}guarantee".format(sub.lineno),
                if check and sub.lineno not in tried:
                    print_dots()
                    tried.add(sub.lineno)
                    act.checked_assert.value = sub.lineno
                    some_failed = False
                    for root in checked_actions:
                        if root in roots:
                           ag = ivy_art.AnalysisGraph()
                           pre = itp.State()
                           pre.clauses = lut.and_clauses(*mod.conjs)
                           with itp.EvalContext(check=False):
                               post = ag.execute_action(root,prestate=pre)
                           fail = itp.State(expr = itp.fail_expr(post.expr))
                           if not check_safety_in_state(mod,ag,fail,report_pass=False):
                               some_failed = True
                               break
                    if not some_failed:
                        print 'PASS'
                else:
                    print ""


def check_isolate():
    temporals = [p for p in im.module.labeled_props if p.temporal]
    mod = im.module
    if temporals:
        if len(temporals) > 1:
            raise IvyError(None,'multiple temporal properties in an isolate not supported yet')
        from ivy_l2s import l2s
        l2s(mod, temporals[0])
        mod.concept_spaces = []
        mod.update_conjs()
    ith.check_theory()
    with im.module.theory_context():
        summarize_isolate(mod)
        return
        check_properties()
        some_temporals = any(p.temporal for p in im.module.labeled_props)
        check_temporals()
        ag = ivy_art.AnalysisGraph(initializer=ivy_alpha.alpha)
        if im.module.initializers:
            cex = ag.check_bounded_safety(ag.states[0])
            if cex is not None:
                display_cex("safety failed in initializer",cex)
        with ivy_interp.EvalContext(check=False):
            initiation_checked = False
            if not some_temporals:
                check_conjectures('Initiation','These conjectures are false initially.',ag,ag.states[0])
                initiation_checked = True
            for actname in get_checked_actions():
                old_checked_assert = act.checked_assert.get()
                assertions = find_assertions(actname)
                if assertions and not initiation_checked:
                    check_conjectures('Initiation','These conjectures are false initially.',ag,ag.states[0])
                    initiation_checked = True
                print "trying {}...".format(actname)
                if act.checked_assert.get():
                    assertions = [a for a in assertions if a.lineno == act.checked_assert.get()]
                tried = set()
                for asn in assertions:
                    if asn.lineno not in tried:
                        tried.add(asn.lineno)
                        act.checked_assert.value = asn.lineno
                        print '{}: {}'.format(asn.lineno,asn)
                        ag.execute_action(actname,prestate=ag.states[0])
                        cex = ag.check_bounded_safety(ag.states[-1],bound=1)
                        if cex is not None:
                            display_cex("safety failed",cex)
                if initiation_checked:
                    print "checking consecution..."
                    ag.execute_action(actname,prestate=ag.states[0],abstractor=ivy_alpha.alpha)
                    check_conjectures('Consecution','These conjectures are not inductive.',ag,ag.states[-1])
                act.checked_assert.value = old_checked_assert



def check_module():
    # If user specifies an isolate, check it. Else, if any isolates
    # are specificied in the file, check all, else check globally.

    missing = []

    isolate = ivy_compiler.isolate.get()
    if isolate != None:
        isolates = [isolate]
    else:
        isolates = sorted(list(im.module.isolates))
        if len(isolates) == 0:
            isolates = [None]
        else:
            if coverage.get():
                missing = ivy_isolate.check_isolate_completeness()
            
    if missing:
        raise iu.IvyError(None,"Some assertions are not checked")

    for isolate in isolates:
        if isolate != None and isolate in im.module.isolates:
            idef = im.module.isolates[isolate]
            if len(idef.verified()) == 0 or isinstance(idef,ivy_ast.TrustedIsolateDef):
                continue # skip if nothing to verify
        if isolate:
            print "\nIsolate {}:".format(isolate)
        with im.module.copy():
            ivy_isolate.create_isolate(isolate) # ,ext='ext'
            if opt_trusted.get():
                continue
            check_isolate()
    print ''
    if failures > 0:
        raise iu.IvyError(None,"failed checks: {}".format(failures))


def main():
    import signal
    signal.signal(signal.SIGINT,signal.SIG_DFL)
    import ivy_alpha
    ivy_alpha.test_bottom = False # this prevents a useless SAT check
    ivy_init.read_params()
    if len(sys.argv) != 2 or not sys.argv[1].endswith('ivy'):
        usage()
    with im.Module():
        with utl.ErrorPrinter():
            ivy_init.source_file(sys.argv[1],ivy_init.open_read(sys.argv[1]),create_isolate=False)
            check_module()
    print "OK"


if __name__ == "__main__":
    main()

