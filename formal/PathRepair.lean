import GeometricRepair

/-! Lifting local rotations to a path in an immutable tree.

An immutable tree has no shared child pointers or cycles by construction. This
model proves order preservation for rotations at any path; it does not yet
verify the corresponding mutable Python pointer updates or path selection.
-/

namespace GeometricRepair

open Tree

inductive Direction where
  | left | right
  deriving Repr, DecidableEq

def applyAt (f : Tree α → Tree α) : List Direction → Tree α → Tree α
  | [], tree => f tree
  | .left :: path, node left key right => node (applyAt f path left) key right
  | .right :: path, node left key right => node left key (applyAt f path right)
  | _ :: _, empty => empty

theorem applyAt_inorder (f : Tree α → Tree α)
    (preserves : ∀ tree, inorder (f tree) = inorder tree)
    (path : List Direction) (tree : Tree α) :
    inorder (applyAt f path tree) = inorder tree := by
  induction path generalizing tree with
  | nil => exact preserves tree
  | cons direction path ih =>
      cases tree with
      | empty => cases direction <;> rfl
      | node left key right => cases direction <;> simp [applyAt, inorder, ih]

theorem local_repair_anywhere_preserves_order
    (path : List Direction) (shape : PathShape) (tree : Tree α) :
    inorder (applyAt (runRotations (localInstructions shape)) path tree) = inorder tree :=
  applyAt_inorder _ (runRotations_inorder _) path tree

def IsSearchTree [LT α] (tree : Tree α) : Prop :=
  (inorder tree).Pairwise (· < ·)

theorem local_repair_anywhere_preserves_bst [LT α]
    (path : List Direction) (shape : PathShape) (tree : Tree α)
    (ordered : IsSearchTree tree) :
    IsSearchTree (applyAt (runRotations (localInstructions shape)) path tree) := by
  unfold IsSearchTree at *
  rw [local_repair_anywhere_preserves_order]
  exact ordered

def subtreeAt : List Direction → Tree α → Option (Tree α)
  | [], tree => some tree
  | .left :: path, node left _ _ => subtreeAt path left
  | .right :: path, node _ _ right => subtreeAt path right
  | _ :: _, empty => none

def insertAtEmpty (key : α) : Tree α → Tree α
  | empty => node empty key empty
  | tree => tree

def insertAtLeaf (key : α) (path : List Direction) (tree : Tree α) : Tree α :=
  applyAt (insertAtEmpty key) path tree

theorem insertAtLeaf_inorder_length (key : α) (path : List Direction)
    (tree : Tree α) (valid : subtreeAt path tree = some empty) :
    (inorder (insertAtLeaf key path tree)).length = (inorder tree).length + 1 := by
  induction path generalizing tree with
  | nil =>
      simp only [subtreeAt, Option.some.injEq] at valid
      subst tree
      simp [insertAtLeaf, applyAt, insertAtEmpty, inorder]
  | cons direction path ih =>
      cases tree with
      | empty => cases direction <;> simp [subtreeAt] at valid
      | node left value right =>
          cases direction with
          | left =>
              have h := ih left (by simpa [subtreeAt] using valid)
              simp only [insertAtLeaf, applyAt, inorder, List.length_append,
                List.length_singleton] at h ⊢
              omega
          | right =>
              have h := ih right (by simpa [subtreeAt] using valid)
              simp only [insertAtLeaf, applyAt, inorder, List.length_append,
                List.length_singleton] at h ⊢
              omega

theorem insertAtLeaf_key_count [BEq α] (key query : α) (path : List Direction)
    (tree : Tree α) (valid : subtreeAt path tree = some empty) :
    (inorder (insertAtLeaf key path tree)).count query =
      (inorder tree).count query + if key == query then 1 else 0 := by
  induction path generalizing tree with
  | nil =>
      simp only [subtreeAt, Option.some.injEq] at valid
      subst tree
      simp [insertAtLeaf, applyAt, insertAtEmpty, inorder, List.count_cons]
  | cons direction path ih =>
      cases tree with
      | empty => cases direction <;> simp [subtreeAt] at valid
      | node left value right =>
          cases direction with
          | left =>
              have h := ih left (by simpa [subtreeAt] using valid)
              simp only [insertAtLeaf, applyAt, inorder, List.count_append,
                List.count_cons, List.count_nil] at h ⊢
              omega
          | right =>
              have h := ih right (by simpa [subtreeAt] using valid)
              simp only [insertAtLeaf, applyAt, inorder, List.count_append,
                List.count_cons, List.count_nil] at h ⊢
              omega

-- Count each ancestor from the insertion depth down through target + 2.
-- Reaching depth target + 1 ends the recursive walk.
def recursiveWalk (target : Nat) : Nat → Nat
  | 0 => 0
  | depth + 1 =>
      if depth + 1 ≤ target + 1 then 0 else 1 + recursiveWalk target depth

theorem recursiveWalk_exact (target depth : Nat) :
    recursiveWalk target depth = depth - target - 1 := by
  induction depth with
  | zero => simp [recursiveWalk]
  | succ depth ih =>
      simp only [recursiveWalk]
      split
      next h => omega
      next h => rw [ih]; omega

theorem recursiveWalk_matches_counter (target depth : Nat) :
    recursiveWalk target depth = repairVisits depth target := by
  rw [recursiveWalk_exact, repair_visits_exact]

end GeometricRepair
