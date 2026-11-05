import Std

/-! Machine-checked local properties of geometric target repair.

The model uses immutable trees and explicit local rotation instructions. It is
not a proof about Python's object graph or about global random tree height.
-/

namespace GeometricRepair

inductive Tree (α : Type) where
  | empty : Tree α
  | node : Tree α → α → Tree α → Tree α
  deriving Repr

open Tree

def inorder : Tree α → List α
  | empty => []
  | node left key right => inorder left ++ [key] ++ inorder right

def rotateRight : Tree α → Tree α
  | node (node a x b) y c => node a x (node b y c)
  | tree => tree

def rotateLeft : Tree α → Tree α
  | node a x (node b y c) => node (node a x b) y c
  | tree => tree

inductive Rotation where
  | rootLeft | rootRight | leftChildLeft | rightChildRight
  deriving Repr

def applyRotation : Rotation → Tree α → Tree α
  | .rootLeft, tree => rotateLeft tree
  | .rootRight, tree => rotateRight tree
  | .leftChildLeft, node left key right => node (rotateLeft left) key right
  | .rightChildRight, node left key right => node left key (rotateRight right)
  | _, empty => empty

def runRotations : List Rotation → Tree α → Tree α
  | [], tree => tree
  | instruction :: rest, tree => runRotations rest (applyRotation instruction tree)

inductive PathShape where
  | leftLeft | rightRight | leftRight | rightLeft
  deriving Repr

def localBefore (shape : PathShape) (x p g : α) (a b c d : Tree α) : Tree α :=
  match shape with
  | .leftLeft => node (node (node a x b) p c) g d
  | .rightRight => node a g (node b p (node c x d))
  | .leftRight => node (node a p (node b x c)) g d
  | .rightLeft => node a g (node (node b x c) p d)

def localInstructions : PathShape → List Rotation
  | .leftLeft => [.rootRight]
  | .rightRight => [.rootLeft]
  | .leftRight => [.leftChildLeft, .rootRight]
  | .rightLeft => [.rightChildRight, .rootLeft]

theorem rotateRight_inorder (tree : Tree α) : inorder (rotateRight tree) = inorder tree := by
  cases tree with
  | empty => rfl
  | node left key right => cases left <;> simp [rotateRight, inorder, List.append_assoc]

theorem rotateLeft_inorder (tree : Tree α) : inorder (rotateLeft tree) = inorder tree := by
  cases tree with
  | empty => rfl
  | node left key right => cases right <;> simp [rotateLeft, inorder, List.append_assoc]

theorem applyRotation_inorder (instruction : Rotation) (tree : Tree α) :
    inorder (applyRotation instruction tree) = inorder tree := by
  cases instruction <;> cases tree <;>
    simp [applyRotation, inorder, rotateLeft_inorder, rotateRight_inorder]

theorem runRotations_inorder (instructions : List Rotation) (tree : Tree α) :
    inorder (runRotations instructions tree) = inorder tree := by
  induction instructions generalizing tree with
  | nil => rfl
  | cons instruction rest ih =>
      simp [runRotations, ih, applyRotation_inorder]

-- Each trace is applied to a well-formed local path and produces the intended
-- tree. This rules out an invalid rotation silently doing nothing.
def localAfter (shape : PathShape) (x p g : α) (a b c d : Tree α) : Tree α :=
  match shape with
  | .leftLeft => node (node a x b) p (node c g d)
  | .rightRight => node (node a g b) p (node c x d)
  | .leftRight => node (node a p b) x (node c g d)
  | .rightLeft => node (node a g b) x (node c p d)

theorem local_repair_result (shape : PathShape) (x p g : α) (a b c d : Tree α) :
    runRotations (localInstructions shape) (localBefore shape x p g a b c d) =
      localAfter shape x p g a b c d := by
  cases shape <;> rfl

theorem local_repair_preserves_order (shape : PathShape) (x p g : α) (a b c d : Tree α) :
    inorder (runRotations (localInstructions shape) (localBefore shape x p g a b c d)) =
      inorder (localBefore shape x p g a b c d) :=
  runRotations_inorder _ _

theorem local_repair_at_most_two_rotations (shape : PathShape) :
    (localInstructions shape).length ≤ 2 := by
  cases shape <;> decide

-- This is the Python visit counter: the loop makes d - t - 2 visits and,
-- exactly when d > t + 1, the selected ancestor is visited once more.
def repairVisits (depth target : Nat) : Nat :=
  if depth ≤ target + 1 then 0 else (depth - target - 2) + 1

theorem repair_visits_exact (depth target : Nat) :
    repairVisits depth target = depth - target - 1 := by
  unfold repairVisits
  split <;> omega

-- Sum of bit costs over all 2^L equally likely length-L bit strings.
-- At the first bit all strings pay once; the all-one-prefix half recurses.
def totalBitCost : Nat → Nat
  | 0 => 0
  | level + 1 => 2 ^ (level + 1) + totalBitCost level

theorem total_bit_cost_exact (level : Nat) :
    totalBitCost level + 2 = 2 ^ (level + 1) := by
  induction level with
  | zero => decide
  | succ level ih =>
      simp only [totalBitCost, Nat.pow_succ] at *
      omega


-- Explicit complete bit streams and the actual capped leading-ones loop.
def bitStrings : Nat → List (List Bool)
  | 0 => [[]]
  | level + 1 => (bitStrings level).map (false :: ·) ++ (bitStrings level).map (true :: ·)

def sampledBitCost : Nat → List Bool → Nat
  | 0, _ => 0
  | _ + 1, [] => 0
  | _ + 1, false :: _ => 1
  | level + 1, true :: rest => 1 + sampledBitCost level rest

-- The same loop also records the number of leading ones. The Python target
-- is L - move - 1, with natural subtraction implementing max(0, ...).
def sampledMove : Nat → List Bool → Nat
  | 0, _ => 0
  | _ + 1, [] => 0
  | _ + 1, false :: _ => 0
  | level + 1, true :: rest => 1 + sampledMove level rest

def sampledTarget (level : Nat) (bits : List Bool) : Nat :=
  level - sampledMove level bits - 1

theorem sampledMove_bounded (level : Nat) (bits : List Bool) :
    sampledMove level bits ≤ level := by
  induction level generalizing bits with
  | zero => simp [sampledMove]
  | succ level ih =>
      cases bits with
      | nil => simp [sampledMove]
      | cons bit rest =>
          cases bit with
          | false => simp [sampledMove]
          | true =>
              simp only [sampledMove]
              have bound := ih rest
              omega

theorem sampler_cost_from_move (level : Nat) (bits : List Bool)
    (enough : level ≤ bits.length) :
    sampledBitCost level bits = min level (sampledMove level bits + 1) := by
  induction level generalizing bits with
  | zero => simp [sampledBitCost]
  | succ level ih =>
      cases bits with
      | nil => simp at enough
      | cons bit rest =>
          cases bit with
          | false => simp [sampledBitCost, sampledMove]
          | true =>
              have restEnough : level ≤ rest.length := by simpa using Nat.le_of_succ_le_succ enough
              simp only [sampledBitCost, sampledMove]
              rw [ih rest restEnough]
              omega

theorem bitStrings_length (level : Nat) : (bitStrings level).length = 2 ^ level := by
  induction level with
  | zero => rfl
  | succ level ih => simp [bitStrings, ih, Nat.pow_succ, Nat.mul_succ, Nat.mul_zero]

theorem sum_map_one (items : List α) : (items.map (fun _ => (1 : Nat))).sum = items.length := by
  induction items with
  | nil => rfl
  | cons item rest ih => simp [ih, Nat.add_comm]

theorem sum_map_succ (items : List α) (f : α → Nat) :
    (items.map (fun item => 1 + f item)).sum = items.length + (items.map f).sum := by
  induction items with
  | nil => rfl
  | cons item rest ih => simp only [List.map_cons, List.sum_cons, List.length_cons, ih]; omega

theorem sampler_cost_sum (level : Nat) :
    ((bitStrings level).map (sampledBitCost level)).sum = totalBitCost level := by
  induction level with
  | zero => rfl
  | succ level ih =>
      simp only [bitStrings, List.map_append, List.sum_append, List.map_map, Function.comp_def,
        sampledBitCost]
      rw [sum_map_one, sum_map_succ, bitStrings_length, ih]
      simp only [totalBitCost, Nat.pow_succ]
      omega

theorem sampler_exact_expected_bits_scaled (level : Nat) :
    ((bitStrings level).map (sampledBitCost level)).sum + 2 = 2 ^ (level + 1) := by
  rw [sampler_cost_sum, total_bit_cost_exact]

end GeometricRepair
