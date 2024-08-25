module EXPRESSION-SYNTAX
  imports BOOL
  imports ID
  imports INT
  imports FLOAT
  imports STRING


syntax ArithmeticExpression ::= Id | Int | Float | String
                         | ( ArithmeticExpression )        [bracket]
                         | ArithmeticExpression "*" ArithmeticExpression   [left]
                         | ArithmeticExpression "/" ArithmeticExpression   [left]
                         > ArithmeticExpression "+" ArithmeticExpression   [left]
                         | ArithmeticExpression "-" ArithmeticExpression   [left]

syntax BoolExpression ::= Bool
                        | ( BoolExpression )        [bracket]
                        | ArithmeticExpression ">" ArithmeticExpression
                        | ArithmeticExpression "<" ArithmeticExpression
                        | ArithmeticExpression ">=" ArithmeticExpression
                        | ArithmeticExpression "==" ArithmeticExpression
                        | ArithmeticExpression "<=" ArithmeticExpression
                        > BoolExpression "&&" BoolExpression
                        > BoolExpression "||" BoolExpression


syntax Expression ::= ArithmeticExpression
                    > BoolExpression

endmodule

module CSP-SYNTAX 
imports EXPRESSION-SYNTAX 

syntax CSP ::= List{CSPGlobal, ""} [format(%1%2%n%3)]

syntax CSPGlobal ::= Id "::=" CSPProcess ";" [format(%1%2%i%n%3%d%n%4)]

syntax CSPProcess ::= List{CSPStatement, ";"} [format(%1%2%n%3)]
syntax CSPStatement ::= Id ":=" ArithmeticExpression
                      | CSPIO
                      | "wait" "(" Int ")"
                      | "if" BoolExpression "then" CSPProcess ";" "else" CSPProcess ";" "endif"
                      | BoolExpression "->" CSPStatement
                      | "(" CSPProcess ";" ")" "**"
                      | "(" CSPProcess ";" ")" "{" BoolExpression "}" "**"
                      | "(" CSPStatement ")" [bracket]
                      | "log" "(" String ")"
                      | CSPCommunicationInterrupts

syntax CSPIO ::= Id "?" Id
               | Id "!" ArithmeticExpression

syntax CSPCommunicationInterrupts ::= List{CSPCommunicationInterrupt, "$"} [format(%1%n%2%3)]
syntax CSPCommunicationInterrupt ::= CSPIO "-->" CSPProcess ";" [format(%1%2%i%n%3%4%d)]

endmodule

module HYBRID-SYNTAX
imports EXPRESSION-SYNTAX

syntax Hybrid ::= "<" ContinuousAssignments "&" BoolExpression ">" | "placeHolderHybrid"

syntax ContinuousAssignments ::= List{ContinuousAssignment, ","}
syntax ContinuousAssignment ::= Id "'" "=" ArithmeticExpression
endmodule

module HCSP-SYNTAX
imports CSP-SYNTAX
imports HYBRID-SYNTAX

syntax HCSP ::= CSP

syntax CSPStatement ::= Hybrid
                      | Hybrid "|>" "(" CSPCommunicationInterrupts ")"

endmodule

module UML-EXTEND-SYNTAX
imports UML-SYNTAX
imports CSP-SYNTAX

syntax SequenceCoreWithCommont ::= SequenceCore ":waiting" Int 

syntax SequenceStatement ::= "alt" BoolExpression SequenceStatements "end" [format(%1%2%n%d%3%n%4)]

syntax SequenceStatement ::= "alt" BoolExpression SequenceStatements SequenceElses "end"

syntax SequenceStatement ::= "loop" BoolExpression SequenceStatements "end" [format(%1 %2%n%i%3%n%d%4)]

syntax SequenceCoreWithCommont ::= SequenceCore ":" CSPStatement

endmodule

module UML-SYNTAX
imports ID
imports STRING
imports INT

syntax 
SequenceCore ::=
    Id "-[" Color "]>" Id
  | Id "-[" Color "]->" Id
  | Id "<[" Color "]-" Id
  | Id "<-[" Color "]-" Id

syntax
Color ::= r"#[A-Za-z]+" [token]

syntax 
SequenceCoreWithCommont ::= SequenceCore ":" String

syntax
SequenceElse ::= "else" SequenceStatements

syntax
SequenceElses ::= List{SequenceElse, "\n"}

syntax SequenceStatement ::=
    SequenceCore
  | SequenceCoreWithCommont
  | "loop" String SequenceStatements "end" 
  | "opt" String SequenceStatements "end" [format(%1 %2%i%n%3%d%n%4)]
  | "opt" SequenceStatements "end" [format(%1%i%n%2%d%n%3)]
  | "alt" String SequenceStatements SequenceElses "end"
  | "'" "process" Id | "'" Id String // comment
  | "group" String SequenceStatements "end" [format(%1 %2%i%n%3%d%n%4)]

syntax
SequenceStatements ::= List{SequenceStatement, "\n"} [format(%1%n%3)]

syntax
SequenceDiagram ::= SequenceStatements
endmodule


module HCSP-TO-SEQUENCE
  imports HCSP-SYNTAX
  imports UML-SYNTAX
imports UML-EXTEND-SYNTAX
imports LIST 
imports K-EQUAL
imports CSP-SYNTAX

configuration
<hcsp-uml-bx>
<csp-program> $PGM:CSP </csp-program>
<threads>
  <thread multiplicity="*" type="Map" color="blue">
    <thread-id> .K </thread-id>
    <k color="green"> .K </k>
  </thread>
</threads>
<tmp-sequence> .List </tmp-sequence>
<uml-sequence> .SequenceStatements </uml-sequence>
</hcsp-uml-bx>

syntax KItem ::= Id "---" KItem
syntax KItem ::= "process" Id
syntax KItem ::= "#opt" | "#end" | "#loop" | "#alt"
syntax KItem ::= "#ifElse"
// syntax KItem ::= "#interrupt" | "#interruptend"

// # Spawn Threads

rule
<csp-program>  G:Id ::= GS:CSPProcess ; C => C </csp-program>
<threads>
...
(.Bag =>
<thread>
  <thread-id> G ~> .K </thread-id>
  <k> GS ~> .K </k>
</thread>)
...
</threads>
[owise]

rule [assignment]:
<thread-id> P:Id </thread-id>
<k> X:Id := Exp:ArithmeticExpression ; Cspp:CSPProcess => Cspp ... </k>
<tmp-sequence> SD => SD ListItem(' P "Initialize" ) </tmp-sequence>

rule [assignment-with-log]:
<thread-id> P:Id </thread-id>
<k> log( S:String ) ; X:Id := Exp:ArithmeticExpression ; Cspp:CSPProcess => Cspp ... </k>
<tmp-sequence> SD => SD ListItem((P -[#token("#black", "Color")]> P : S):SequenceCoreWithCommont)</tmp-sequence>

rule [channel]:
<thread>
  <thread-id> Send:Id </thread-id>
  <k> Channel ! E:ArithmeticExpression ; X0:CSPProcess => X0 ... </k>
</thread>
<thread>
  <thread-id> Recieve:Id </thread-id>
  <k> Channel ? I:Id ; X1:CSPProcess => X1 ... </k>
</thread>
<tmp-sequence> SD => SD ListItem(Send -[#token("#black", "Color")]> Recieve : I := E) </tmp-sequence>

rule [wait]:
<thread>
  <thread-id> P:Id </thread-id>
  <k> wait(I:Int) ; X:CSPProcess => X ...</k>
</thread>
<tmp-sequence> SD => SD ListItem(P -[#token("#black", "Color")]> P :waiting I) </tmp-sequence>

rule [if-then]:
<thread>
  <thread-id> P:Id </thread-id>
  <k> BE:BoolExpression -> ST:CSPStatement; X:CSPProcess => ST ; .CSPProcess ~> #end ~> X ... </k>
</thread>
<tmp-sequence> SD => SD ListItem(#alt) ListItem(BE) </tmp-sequence>

rule [if-then-else]:
<thread-id> P:Id </thread-id>
<k> if BE:BoolExpression then CS0:CSPProcess ; else CS1:CSPProcess ; endif  ; X:CSPProcess
    => CS0 ~> #ifElse ~> CS1 ~> #end ~> X </k>
<tmp-sequence> SD => SD ListItem(#alt) ListItem(BE) </tmp-sequence>

rule [if-else]:
<k> #ifElse </k>
<tmp-sequence> SD => SD ListItem(#ifElse) </tmp-sequence>

// "(" CSPProcess ";" ")" "**"
rule [endless-loop]:
<thread>
  <thread-id> P:Id </thread-id>
  <k> ( C:CSPProcess; )** ; X:CSPProcess => C ~> #end ~> X ... </k>
</thread>
<tmp-sequence> SD:List => SD ListItem(#loop) ListItem(true) </tmp-sequence>

// "(" CSPProcess ";" ")" "{" BoolExpression "}" "**"
rule [normal-loop]:
<thread>
  <thread-id> P:Id </thread-id>
  <k> ( C:CSPProcess; ){BE:BoolExpression}**; X:CSPProcess => C ~> #end ~> X ... </k>
</thread>
<tmp-sequence> SD => SD ListItem(#loop) ListItem(BE) </tmp-sequence>

// CSPCommunicationInterrupts

// rule [csp-communication-interrupt-startup]:
// <k> CSPCI:CSPCommunicationInterrupts ; Cspp:CSPProcess => CSPCI ~> intt ~> Cspp ... </k>
// <tmp-sequence> SD => SD ListItem("interrupt") </tmp-sequence>

rule [csp-communication-interrupt]:
<thread-id> P:Id </thread-id>
<k> CIO:CSPIO --> CP:CSPProcess ; $ CSPCI:CSPCommunicationInterrupts ; Cspp:CSPProcess => CIO ; CP ~> #end ~> CSPCI ; Cspp ... </k>
<tmp-sequence> SD => SD ListItem(#opt) </tmp-sequence>

rule [csp-communication-interrupt-last]:
<thread-id> P:Id </thread-id>
<k> CIO:CSPIO --> CP:CSPProcess ; $ .CSPCommunicationInterrupts ; Cspp:CSPProcess => CIO ; CP ~> #end ~> Cspp ... </k>
<tmp-sequence> SD => SD ListItem(#opt) </tmp-sequence>
[priority(48)]


// Hybrid
rule [hybrid]:
<thread>
  <thread-id> P:Id </thread-id>
  <k> log( S:String ) ; H:Hybrid ; X:CSPProcess => X ... </k>
</thread>
<tmp-sequence> SD => SD ListItem(P -[#token("#black", "Color")]> P : S) </tmp-sequence>

// Hybrid "|>" "(" CSPCommunicationInterrupts ")"
syntax KItem ::= "#hybrid-interrupts" "(" String "," Hybrid ")"

rule [hybrid-csp-communication-interrupts]:
<k> H:Hybrid |> (CSPCI:CSPCommunicationInterrupts) ; X:CSPProcess => CSPCI ~> X ... </k>
// <tmp-sequence> SD => SD ListItem("hybrid-interrupt") </tmp-sequence>
[owise]

// # Join Threads

rule
(
<thread>
  <thread-id> P:Id </thread-id>
  <k> .CSPProcess </k>
</thread>
=> .Bag)
<tmp-sequence> SD => SD ListItem(' process P )</tmp-sequence>
[priority(48)]

rule <k> .CSPProcess => . ...</k> 
     <tmp-sequence> L => L ListItem(.SequenceStatements) </tmp-sequence>
rule <k> #end => . ...</k> 
     <tmp-sequence> L => L ListItem(#end) </tmp-sequence>
// # Sugar the list of UML sequence statements
rule <tmp-sequence> L ListItem(X:SequenceStatement) => L ListItem(X) ListItem(.SequenceStatements) </tmp-sequence> [priority(205)]
rule <tmp-sequence> ListItem(.SequenceStatements) ListItem(Xs:SequenceStatements) => ListItem(Xs:SequenceStatement) </tmp-sequence> [group(bx)]
rule <tmp-sequence> L ListItem(X:SequenceStatement) ListItem(Xs:SequenceStatements) => L ListItem(X Xs) </tmp-sequence> [priority(40)]
rule <tmp-sequence> L ListItem(#opt) ListItem(Xs:SequenceStatements) ListItem(#end)
     => L ListItem(opt Xs end) </tmp-sequence> [priority(42)]
rule <tmp-sequence> L ListItem(#loop) ListItem(BE:BoolExpression) ListItem(Xs:SequenceStatements) ListItem(#end)
      => L ListItem(loop BE Xs end) </tmp-sequence> [priority(42)]
rule <tmp-sequence> L ListItem(#alt) ListItem(BE:BoolExpression) ListItem(Xs:SequenceStatements) ListItem(#end)
      => L ListItem(alt BE Xs end) </tmp-sequence> [priority(42)]
rule <tmp-sequence> L ListItem(#alt) ListItem(BE:BoolExpression) ListItem(Xs:SequenceStatements) ListItem(#ifElse) ListItem(Xss:SequenceStatements) ListItem(#end)
      => L ListItem(alt BE Xs else Xss end) </tmp-sequence> [priority(42)]

rule <tmp-sequence> ListItem(Xs:SequenceStatements) => .List </tmp-sequence>
     <uml-sequence> .SequenceStatements => Xs </uml-sequence> [priority(210)]

endmodule

