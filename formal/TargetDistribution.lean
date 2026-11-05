import GeometricRepair

/-! Exact target-frequency results over uniformly enumerated fair-bit strings.

This is a finite counting model of the sampler. It does not formalize the
Python runtime, adaptive tree processes, or the strong law of large numbers.
-/

namespace GeometricRepair

def targetCount (level target : Nat) : Nat :=
  ((bitStrings level).filter (fun bits => sampledTarget level bits == target)).length

def targetAtMostCount (level bound : Nat) : Nat :=
  ((bitStrings level).filter (fun bits => sampledTarget level bits ≤ bound)).length

theorem sampled_target_false (level : Nat) (bits : List Bool) :
    sampledTarget (level + 1) (false :: bits) = level := by
  simp [sampledTarget, sampledMove]

theorem sampled_target_true_false (level : Nat) (bits : List Bool) :
    sampledTarget (level + 2) (true :: false :: bits) = level := by
  simp [sampledTarget, sampledMove]

theorem sampled_target_true_true (level : Nat) (bits : List Bool) :
    sampledTarget (level + 3) (true :: true :: bits) ≤ level := by
  simp only [sampledTarget, sampledMove]
  omega

def topTargetStreams (level : Nat) : List (List Bool) :=
  (bitStrings (level + 2)).map (false :: ·)

def secondTargetStreams (level : Nat) : List (List Bool) :=
  (bitStrings (level + 1)).map (fun bits => true :: false :: bits)

def lowerTargetStreams (level : Nat) : List (List Bool) :=
  (bitStrings (level + 1)).map (fun bits => true :: true :: bits)

theorem target_streams_partition (level : Nat) :
    bitStrings (level + 3) =
      topTargetStreams level ++ secondTargetStreams level ++ lowerTargetStreams level := by
  simp [topTargetStreams, secondTargetStreams, lowerTargetStreams, bitStrings,
    List.map_append, List.map_map, Function.comp_def, List.append_assoc]

theorem target_stream_lengths (level : Nat) :
    (topTargetStreams level).length = 2 ^ (level + 2) ∧
    (secondTargetStreams level).length = 2 ^ (level + 1) ∧
    (lowerTargetStreams level).length = 2 ^ (level + 1) := by
  simp [topTargetStreams, secondTargetStreams, lowerTargetStreams, bitStrings_length]

theorem top_stream_target (level : Nat) (bits : List Bool)
    (member : bits ∈ topTargetStreams level) :
    sampledTarget (level + 3) bits = level + 2 := by
  obtain ⟨tail, _, rfl⟩ := List.mem_map.mp member
  exact sampled_target_false (level + 2) tail

theorem second_stream_target (level : Nat) (bits : List Bool)
    (member : bits ∈ secondTargetStreams level) :
    sampledTarget (level + 3) bits = level + 1 := by
  obtain ⟨tail, _, rfl⟩ := List.mem_map.mp member
  exact sampled_target_true_false (level + 1) tail

theorem lower_stream_target (level : Nat) (bits : List Bool)
    (member : bits ∈ lowerTargetStreams level) :
    sampledTarget (level + 3) bits ≤ level := by
  obtain ⟨tail, _, rfl⟩ := List.mem_map.mp member
  exact sampled_target_true_true level tail

end GeometricRepair
