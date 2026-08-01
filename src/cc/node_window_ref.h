#ifndef SRC_CC_NODE_WINDOW_REF_H__
#define SRC_CC_NODE_WINDOW_REF_H__

#include <vector>

#include "src/cc/ref_callback.h"

namespace bidirectional {

/// Per-resource propagation policy for NodeWindowREF
enum ResourcePolicy : int {
  /// new = cum + edge + node_consumption[head] (engine-compatible additive)
  POLICY_ADDITIVE = 0,
  /// Time-like: wait until node lower bound, reject above upper bound
  POLICY_WINDOW_WAIT = 1,
  /// Reject both below lower bound and above upper bound (no waiting)
  POLICY_WINDOW_HARD = 2
};

/**
 * Native (C++-only, non-director) REF implementing per-node resource windows
 * [lb, ub] and per-node consumption. Time windows = WINDOW_WAIT on the time
 * resource with node_consumption = service time (added on departure from the
 * tail node). The propagated value of a WINDOW_WAIT resource is the service
 * start time at the node: T_head = max(lb_head, T_tail + cons_tail + edge).
 *
 * Requirements (validated in setResourcePolicy / Python-side checking):
 *  - node ids are the internal contiguous ids 0..number_vertices-1
 *  - the critical resource (index critical_res) MUST stay POLICY_ADDITIVE
 *    with all-zero node_consumption (docs/ref.rst monotonicity requirements
 *    and the REF_join fix-up in labelling.cc rely on this)
 *  - max_res passed here must be the exact same values given to BiDirectional
 *  - max_res[r] must be FINITE for any resource configured with a window
 *    policy (WINDOW_WAIT / WINDOW_HARD): the rejection sentinel must exceed
 *    max_res[r] (with +inf the engine check `res <= max_res` cannot reject),
 *    and REF_bwd uses H - ub arithmetic that would produce NaN with an
 *    infinite horizon. Enforced in setResourcePolicy.
 *  - WINDOW_HARD: REF_bwd/REF_join only track the latest-feasible-value
 *    recursion (upper bounds); interior lower bounds cannot be checked
 *    backwards without waiting. Only use WINDOW_HARD with forward search
 *    (enforced on the Python side) unless all lower bounds are non-binding.
 *
 * Ownership: the caller (Python wrapper) owns instances; Params never deletes
 * its ref_callback pointer (see Params::~Params: the pointer is set to
 * nullptr before delete, i.e. a no-op). Keep the instance alive for the whole
 * lifetime of the BiDirectional object using it.
 */
class NodeWindowREF final : public REFCallback {
 public:
  NodeWindowREF(
      const int&                 number_vertices,
      const std::vector<double>& max_res, // n_res inferred from size
      const int&                 source_id, // internal integer id of Source
      const int&                 sink_id,   // internal integer id of Sink
      const int&                 critical_res = 0,
      const double&              eps          = 1e-9);
  ~NodeWindowREF() override = default;

  /**
   * Configure resource r. Unconfigured resources default to POLICY_ADDITIVE
   * with zero node data (== engine default additive REF).
   * All three vectors must have size number_vertices, indexed by internal id.
   * Throws std::invalid_argument on bad input (r out of range, size mismatch,
   * invalid policy, lb[v] > ub[v], or non-additive policy/nonzero consumption
   * on the critical resource).
   */
  void setResourcePolicy(
      const int&                 r,
      const int&                 policy, // ResourcePolicy value
      const std::vector<double>& lower,  // lb[r][v]
      const std::vector<double>& upper,  // ub[r][v]
      const std::vector<double>& node_consumption); // c[r][v]

  std::vector<double> REF_fwd(
      const std::vector<double>& cumulative_resource,
      const int&                 tail,
      const int&                 head,
      const std::vector<double>& edge_resource_consumption,
      const std::vector<int>&    partial_path,
      const double&              accummulated_cost) const override;

  std::vector<double> REF_bwd(
      const std::vector<double>& cumulative_resource,
      const int&                 tail,
      const int&                 head,
      const std::vector<double>& edge_resource_consumption,
      const std::vector<int>&    partial_path,
      const double&              accummulated_cost) const override;

  std::vector<double> REF_join(
      const std::vector<double>& fwd_resource,
      const std::vector<double>& bwd_resource,
      const int&                 tail,
      const int&                 head,
      const std::vector<double>& edge_resource_consumption) const override;

 private:
  /**
   * Cheap argument guards for the (Python-exposed) REF methods: node ids in
   * [0, number_vertices) and resource vectors of size >= n_res. The engine
   * always passes valid arguments; these protect direct Python calls from
   * out-of-bounds reads / crashes. Throws std::invalid_argument.
   */
  void checkExtensionArgs(
      const std::vector<double>& resource_vector,
      const int&                 tail,
      const int&                 head,
      const std::vector<double>& edge_resource_consumption) const;

  int                 n_vertices_;
  int                 n_res_;
  int                 source_id_;
  int                 sink_id_;
  int                 critical_res_;
  double              eps_;
  std::vector<double> max_res_;  // H_r (global horizon, same as engine's)
  std::vector<double> sentinel_; // rejection sentinel (> max_res[r])
  std::vector<int>    policy_;   // n_res, default POLICY_ADDITIVE
  std::vector<std::vector<double>> lb_;   // [r][v], default 0
  std::vector<std::vector<double>> ub_;   // [r][v], default H_r
  std::vector<std::vector<double>> cons_; // [r][v], default 0
};

} // namespace bidirectional

#endif // SRC_CC_NODE_WINDOW_REF_H__
