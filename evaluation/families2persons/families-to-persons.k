module FAMILIES-TO-PERSONS-SYNTAX
imports ID
imports STRING
imports LIST

syntax Families ::= List{Family,","} [format(%1%2%n%3)]
syntax Family ::= "Family" "{" "familyName" "=" Id "," "father" "=" FamilyMemberOption "," "mother" "=" FamilyMemberOption "," "sons" "=" FamilyMembers "," "daughters" "=" FamilyMembers "}" [format(%1%2%n%i%3%4%5%6%n%7%8%9%10%n%11%12%13%14%n%15%16%17%18%n%19%20%21%d%n%22)]
syntax FamilyMemberOption ::= "Nothing" | FamilyMember
syntax FamilyMembers ::= List{FamilyMember,","} [format(%1%2 %3)]
syntax FamilyMember ::= "{" "firstName" "=" Id "}"

syntax Persons ::= List{Person,","} [format(%1%2%n%3)]
syntax Person ::= "Male" PersonInfo | "Female" PersonInfo
syntax PersonInfo ::= "{" "fullName" "=" Id Id "," "birthday" "=" String "}"

endmodule

module FAMILIES-TO-PERSONS
imports FAMILIES-TO-PERSONS-SYNTAX
// son > father > daughter > mother
configuration
<T>
  <k> $PGM:Families </k>
  <order> .List </order>
  <person> .Persons </person>
</T>

rule <k> Family { familyName = Fid, father = F:FamilyMember, mother = M:FamilyMember, sons = Ss, daughters = {firstName = Name} , Ds } , Fs:Families => Family { familyName = Fid, father = F, mother = M, sons = Ss, daughters = Ds } , Fs </k>
     <person> Ps => Female { fullName = Fid Name, birthday = "0001-01-01"} , Ps </person>

rule <k> Family { familyName = Fid, father = F:FamilyMember, mother = M:FamilyMember, sons = {firstName = Name} , Ss , daughters = .FamilyMembers } , Fs:Families => Family { familyName = Fid, father = F, mother = M, sons = Ss, daughters = .FamilyMembers } , Fs </k>
     <person> Ps => Male { fullName = Fid Name, birthday = "0001-01-01"} , Ps </person>

rule <k> Family { familyName = Fid, father = F, mother = {firstName = Name} , sons = .FamilyMembers , daughters = .FamilyMembers } , Fs:Families => Family { familyName = Fid, father = F, mother = Nothing, sons = .FamilyMembers, daughters = .FamilyMembers } , Fs </k>
     <person> Ps => Female { fullName = Fid Name, birthday = "0001-01-01"} , Ps </person>

rule <k> Family { familyName = Fid, father = {firstName = Name}, mother = Nothing, sons = .FamilyMembers , daughters = .FamilyMembers } , Fs:Families => Fs </k>
     <person> Ps => Male { fullName = Fid Name, birthday = "0001-01-01"} , Ps </person>

rule <k> Family { familyName = Fid, father = Nothing, mother = Nothing, sons = .FamilyMembers , daughters = .FamilyMembers } , Fs:Families => Fs </k>
     <order> L => ListItem(Fid) L </order>

endmodule