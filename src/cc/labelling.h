#ifndef SRC_CC_LABELLING_H__
#define SRC_CC_LABELLING_H__

#include <algorithm> // copy
#include <cmath>     // nan
#include <cstdint>   // uint64_t
#include <set>
#include <vector>

#include "src/cc/config.h"  // log-level
#include "src/cc/digraph.h" // AdjVertex
#include "src/cc/params.h"  // Directions, Params
                            //
// logging
#include "spdlog/spdlog.h" // after config.h as

namespace labelling {

/**
 * Immutable bit set over the required nodes visited by a label, used only
 * when `Params::require_all_visits` is true.
 *
 * Every label carries one of these, including the labels of the users that
 * never enable the mandatory-visit mode, so the representation is kept as
 * small and as allocation free as possible:
 *   - at most 64 required nodes (one word), which covers every instance that
 *     an exact labelling algorithm can solve in practice, the word is stored
 *     inline and no heap allocation takes place;
 *   - beyond 64 required nodes a heap array is used;
 *   - when the mandatory-visit mode is disabled the bit set holds zero words
 *     and no heap allocation takes place either.
 * The word count is stored in the object so that copying and comparison are
 * self contained (labels are stored and compared by value).
 */
class RequiredVisitMask {
 public:
  RequiredVisitMask() = default;
  ~RequiredVisitMask() { deallocate(); }
  RequiredVisitMask(const RequiredVisitMask& other) { copyFrom(other); }
  RequiredVisitMask(RequiredVisitMask&& other) noexcept { stealFrom(other); }
  RequiredVisitMask& operator=(const RequiredVisitMask& other) {
    if (this != &other) {
      deallocate();
      copyFrom(other);
    }
    return *this;
  }
  RequiredVisitMask& operator=(RequiredVisitMask&& other) noexcept {
    if (this != &other) {
      deallocate();
      stealFrom(other);
    }
    return *this;
  }

  /// Number of 64-bit words held.
  int size() const { return num_words_; }
  /// Read access to the words. Only the first `size()` entries are valid.
  const std::uint64_t* words() const {
    return num_words_ > 1 ? storage_.heap : &storage_.inlined;
  }
  /// Discard the contents and hold `n_words` zeroed words.
  void reset(const int& n_words) {
    deallocate();
    num_words_ = n_words;
    if (n_words > 1)
      storage_.heap = new std::uint64_t[n_words]();
  }
  /// Set bit `b`. The caller guarantees `b < 64 * size()`.
  void setBit(const int& b) {
    if (num_words_ > 1)
      storage_.heap[b >> 6] |= (1ULL << (b & 63));
    else
      storage_.inlined |= (1ULL << (b & 63));
  }
  bool operator==(const RequiredVisitMask& other) const {
    if (num_words_ != other.num_words_)
      return false;
    if (num_words_ <= 1) // also covers the empty (disabled) case
      return storage_.inlined == other.storage_.inlined;
    for (int i = 0; i < num_words_; ++i)
      if (storage_.heap[i] != other.storage_.heap[i])
        return false;
    return true;
  }
  bool operator!=(const RequiredVisitMask& other) const {
    return !(*this == other);
  }

 private:
  union Storage {
    std::uint64_t  inlined;
    std::uint64_t* heap;
  };

  void deallocate() {
    if (num_words_ > 1)
      delete[] storage_.heap;
    num_words_       = 0;
    storage_.inlined = 0ULL;
  }
  void copyFrom(const RequiredVisitMask& other) {
    num_words_ = other.num_words_;
    if (num_words_ > 1) {
      storage_.heap = new std::uint64_t[num_words_];
      std::copy(
          other.storage_.heap,
          other.storage_.heap + num_words_,
          storage_.heap);
    } else {
      storage_.inlined = other.storage_.inlined;
    }
  }
  void stealFrom(RequiredVisitMask& other) {
    num_words_             = other.num_words_;
    storage_               = other.storage_;
    other.num_words_       = 0;
    other.storage_.inlined = 0ULL;
  }

  int     num_words_ = 0;
  Storage storage_   = {0ULL};
};

/**
 * Single node label. With resource, cost and other attributes.
 *
 * Main functionality includes:
 *   - Checking resource feasibility
 *   - Checking dominance
 */
class Label {
 public:
  double                weight               = 0.0;
  bidirectional::Vertex vertex               = {-1, -1};
  std::vector<double>   resource_consumption = {};
  std::vector<int>      partial_path         = {};
  /**
   * Unreachable nodes, held as a SORTED vector of user ids. Only used in the
   * elementary case.
   *
   * This was a std::set<int>. The operations it serves are: rebuild from the
   * partial path at construction, one membership test per extension, one
   * ordered insert per infeasible extension, and -- by far the hottest -- a
   * subset test (std::includes) against another label's list inside the
   * dominance check, run once per label pair. A sorted vector serves all of
   * those with contiguous memory: std::includes walks two arrays instead of
   * chasing red-black tree nodes (which was ~30% of the whole search on a
   * pricing-shaped instance), copying a label copies one buffer instead of
   * rebuilding a tree node by node, and the ordered insert's O(n) shift is
   * cheap at these sizes (a handful to a few dozen ids).
   *
   * Invariant: sorted ascending, no duplicates. Everything that writes it
   * (the constructors and Label::extend) maintains this; std::includes and
   * std::binary_search rely on it.
   */
  std::vector<int> unreachable_nodes = {};
  /**
   * Bit set over the required nodes visited by `partial_path`.
   * Bit `params_ptr->required_bit_by_user_id[u]` is set when user id `u`
   * appears in `partial_path`. This is only used when
   * `params_ptr->require_all_visits` is true; otherwise it holds zero words
   * (no allocation) and the label behaves exactly as before.
   * Unlike `unreachable_nodes`, this member is never modified after
   * construction, so it always represents the visited set of the label.
   */
  RequiredVisitMask      required_visited_mask = {};
  bidirectional::Params* params_ptr            = nullptr;
  // Phi value for joining algorithm from Righini and Salani (2006)
  double phi = std::nan("nan");

  /* Constructors */
  /// Dummy constructor
  Label(){};

  /// Constructor
  Label(
      const double&                weight_in,
      const bidirectional::Vertex& vertex_in,
      const std::vector<double>&   resource_consumption_in,
      const std::vector<int>&      partial_path_in,
      bidirectional::Params*       params);

  /// @overload with phi
  Label(
      const double&                weight_in,
      const bidirectional::Vertex& vertex_in,
      const std::vector<double>&   resource_consumption_in,
      const std::vector<int>&      partial_path_in,
      bidirectional::Params*       params,
      const double&                phi_in);

  /**
   * @overload for the extension of `parent` along a single edge.
   *
   * `partial_path_in` must be the partial path of `parent` followed by
   * `vertex_in`, so the required-visit bit set is the one of `parent` with at
   * most one extra bit. Inheriting it avoids re-scanning the whole partial
   * path on every extension.
   */
  Label(
      const double&                weight_in,
      const bidirectional::Vertex& vertex_in,
      const std::vector<double>&   resource_consumption_in,
      const std::vector<int>&      partial_path_in,
      bidirectional::Params*       params,
      const Label&                 parent);

  /* Special members.
   *
   * All five are spelled out because the user-declared destructor used to be
   * `~Label(){};`, which suppresses the implicit move operations: every heap
   * sift in the unprocessed-label heap, every erase-shift in the efficient
   * label vectors and every vector reallocation then deep-copied the two
   * vectors and the unreachable_nodes set of every label it touched. The
   * moves are noexcept (every member's move is), so vector reallocation
   * actually uses them.
   */
  Label(const Label&)            = default;
  Label(Label&&) noexcept        = default;
  Label& operator=(const Label&) = default;
  Label& operator=(Label&&) noexcept = default;
  ~Label()                       = default;

  /**
   * Generate new label extensions from the current label and return only if
   * resource feasible.
   * The input label is a pointer as it may be modified in
   * the case that the edge / adjacent_vertex is found to be resource
   * infeasible, in which case, the head/tail node becomes unreachable and the
   * attribute is updated.
   *
   * @param[out] label, labelling::Label, current label to extend (and maybe
   * update `unreachable_nodes`)
   * @param[in] adjacent_vertex, AdjVertex, edge
   * @param[in] direction Directions
   * @param[in] elementary bool
   * @param[in] max_res, vector of double with upper bound(s) for resource
   * consumption
   * @param[in] min_res, vector of double with lower bound(s) for resource
   * consumption
   *
   * @return Label object with extended label. Note this may be empty if the
   * extension is resource infeasible
   */
  Label extend(
      const bidirectional::AdjVertex&  adjacent_vertex,
      const bidirectional::Directions& direction,
      const std::vector<double>&       max_res = {},
      const std::vector<double>&       min_res = {});

  /**
   * Check if this dominates other.
   * Assumes the labels are comparable i.e. same nodes
   *
   * @param[in] other Label
   * @param[in] direction Directions
   * @param[in] elementary bool, optional
   * @return bool
   */
  bool checkDominance(
      const Label&                     other,
      const bidirectional::Directions& direction) const;

  /**
   * Checks whether `this` dominates `other` for the input direction. In the
   * case when neither dominates , i.e. they are non-dominated, the direction is
   * flipped labels are compared again.
   *
   * @param[in] other Label
   * @param[in] direction Directions
   * @param[in] elementary bool
   * @return bool
   */
  bool fullDominance(
      const Label&                     other,
      const bidirectional::Directions& direction) const;

  /**
   * Check resource feasibility of current label i.e. `min_res[i] <=
   * resource_consumption[i] <= max_res[i]` for `i` in
   * `0,...,resource_consumption.size()`.
   * If "soft" check, then the lower bound is only checked if either: resource
   * index `i` is the index of the critical resource or `min_res[i]<= 0`(See
   * issue #90). If not "soft", then all lower bounds are checked as expected.
   *
   * @param[in] max_res, vector of double with upper bound(s) for resource
   * consumption. Checks values are <= bound
   * @param[in] min_res, vector of double with lower bound(s) for resource
   * consumption. Checks values are >= bound
   * @param[in] soft, bool with whether the minimum resources should be checked
   * "softly". Default is false.
   */
  bool checkFeasibility(
      const std::vector<double>& max_res,
      const std::vector<double>& min_res,
      const bool&                soft = false) const;

  /**
   * Check if weight meets the input threshold.
   *
   * @param[in] threshold, double with the acceptance threshold.
   * @param[in] strict, bool. When false (default) the label meets the
   * threshold when `weight <= threshold`; when true only when
   * `weight < threshold` (strictly better than the threshold, e.g. a known
   * incumbent value).
   */
  bool checkThreshold(const double& threshold, const bool& strict = false)
      const;

  /**
   * Check whether the current partial path is Source - Sink
   *
   * @param[in] source_id, int with user_id of the source node.
   * @param[in] sink_id, int with user_id of the sink node.
   */
  bool checkStPath(const int& source_id, const int& sink_id) const;

  /// Returns true is the partial path extension is OK.
  bool checkPathExtension(const int& user_id) const;

  /**
   * Simple check if both lables have the same feasible extension with regard to
   * 2-cycle elimination.
   * this and other have same feasible extension if predecessor is the same.
   * @param[in] other, Label with other label to compare
   * @return true if this and other have same feasible extension
   */
  bool checkSameFeasibleExtensionTwoCycleSimple(const Label& other) const;

  /**
   * Simple check if both lables have the same feasible extension under
   * elementary conditions.
   * this and other have the same feasible extension if unreachable_nodes of
   * this is subset of unreachable_nodes of other
   * @param[in] other, Label with other label to compare
   * @return true if this and other have same feasible extension
   */
  bool checkSameFeasibleExtensionElementary(const Label& other) const;

  /**
   * Check if both lables have the same feasible extension, i.e.,
   * if they both can extend to the same nodes.
   * Important for correct dominance check.
   * Labels with different feasible extension cannot dominate each other.
   * @param[in] other, Label with other label to compare
   * @return true if this and other have same feasible extension
   */
  bool checkSameFeasibleExtension(const Label& other) const;

  /**
   * Check whether every required node has already been visited by the
   * partial path of this label.
   * Only meaningful when `params_ptr->require_all_visits` is true.
   *
   * Precondition: `params_ptr != nullptr`, i.e. the label was built with one
   * of the constructors that take the parameters and not with the dummy
   * constructor. This matches `checkFeasibility` and `checkPathExtension`.
   *
   * @return true if the visited set covers the whole required set
   */
  bool checkAllRequiredVisited() const;

  /**
   * Check whether both labels visit exactly the same required nodes.
   * Only meaningful when `params_ptr->require_all_visits` is true.
   *
   * Precondition: `params_ptr != nullptr` (see `checkAllRequiredVisited`).
   *
   * @param[in] other, Label with other label to compare
   * @return true if the two required-visit bit sets are equal
   */
  bool checkSameRequiredVisits(const Label& other) const;

  /// set phi attribute for merged labels from Righini and Salani (2006)
  void setPhi(const double& phi_in) { phi = phi_in; }

  /// gets the id of the predecessor node
  /// TODO can be replaced as member of label
  int getPredecessorId() const { return partial_path.end()[-2]; };

  std::string getString() const;
  // operator overloads
  friend bool          operator<(const Label& label1, const Label& label2);
  friend bool          operator>(const Label& label1, const Label& label2);
  friend std::ostream& operator<<(std::ostream& os, const Label& label);
  friend bool          operator==(const Label& label1, const Label& label2);
  friend bool          operator!=(const Label& label1, const Label& label2) {
             return !(label1 == label2);
  }

 private:
  /**
   * Set the bit of user id `user_id` in `required_visited_mask` when that
   * vertex belongs to the required set. No-op otherwise.
   * Only called when `params_ptr->require_all_visits` is true.
   */
  void setRequiredVisitBit(const int& user_id);
};

/**
 * Get next label from ordered labels
 * Grabs the next element in the heap (back) and removes it
 * In the forward (backward) direction this is the label with lowest (highest)
 * monotone resource.
 *
 * @param[out] labels, std::vector<Label> pointer (heap)
 * @param[in] direction, Directions
 */
Label getNextLabel(
    std::vector<Label>*              labels,
    const bidirectional::Directions& direction);

/**
 * Check whether the input label dominates any efficient label (previously
 * undominated labels) at the same node.
 * If any label is dominated by the input label, they are removed.
 *
 * @param[out] efficient_labels, pointer to a vector of Label with the efficient
 * labels at the same node as `label`. If a label is dominated by `label`, it is
 * removed from this vector.
 * @param[in] label, Label to compare
 * @param[in] direction, Directions with direction of search
 * @param[in] elementary, bool with whether non-elementary paths are allowed
 *
 * @return bool, true if `label` is dominated, false otherwise
 */
bool runDominanceEff(
    std::vector<Label>*              efficient_labels_ptr,
    const Label&                     label,
    const bidirectional::Directions& direction,
    const bool&                      elementary);

/**
 * Reverse backward path and inverts resource consumption
 * and returns resulting forward-compatible label.
 *
 * @param[out] label, labelling::Label, current label to extend (and maybe
 * update `unreachable_nodes`)
 * @param[in] max_res, vector of double with upper bound(s) for resource
 * consumption. To use to invert monotone resource
 * @param[in] invert_min_res, bool
 *
 * @return inverted label
 */
Label processBwdLabel(
    const labelling::Label&    label,
    const std::vector<double>& max_res,
    const std::vector<double>& cumulative_resource,
    const bool&                invert_min_res = false);

/**
 * Check whether a pair of forward and backward labels are suitable for merging.
 * To be used before attempting to merge.
 */
bool mergePreCheck(
    const labelling::Label&    fwd_label,
    const labelling::Label&    bwd_label,
    const std::vector<double>& max_res);

/**
 * Returns the phi value.
 * As defined in Righini and Salani (2006)
 */
double getPhiValue(
    const labelling::Label&    fwd_label,
    const labelling::Label&    bwd_label,
    const std::vector<double>& max_res);

/**
 * Check whether the pair (phi, path) is already contained in all the (phi,
 * path) pairs with a lower phi.
 *
 * As defined in Righini and Salani (2006)
 */
bool halfwayCheck(const Label& label, const std::vector<Label>& labels);

/**
 * Merge labels produced by a backward and forward label.
 * If an s-t compatible path can be obtained the appropriately
 * extended and merged label is returned.
 *
 * @return merged label with updated attributes and new phi value.
 */
Label mergeLabels(
    const labelling::Label&         fwd_label,
    const labelling::Label&         bwd_label,
    const bidirectional::AdjVertex& adj_vertex,
    const bidirectional::Vertex&    sink,
    const std::vector<double>&      max_res,
    const std::vector<double>&      min_res);

} // namespace labelling

#endif // SRC_CC_LABELLING_H__
