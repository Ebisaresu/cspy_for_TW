#include "src/cc/node_window_ref.h"

#include <algorithm> // max
#include <cmath>     // nextafter
#include <limits>    // numeric_limits
#include <stdexcept> // invalid_argument
#include <string>

namespace bidirectional {

NodeWindowREF::NodeWindowREF(
    const int&                 number_vertices,
    const std::vector<double>& max_res,
    const int&                 source_id,
    const int&                 sink_id,
    const int&                 critical_res,
    const double&              eps)
    : n_vertices_(number_vertices),
      n_res_(static_cast<int>(max_res.size())),
      source_id_(source_id),
      sink_id_(sink_id),
      critical_res_(critical_res),
      eps_(eps),
      max_res_(max_res) {
  if (n_vertices_ <= 0) {
    throw std::invalid_argument("[NodeWindowREF] number_vertices must be > 0");
  }
  if (n_res_ <= 0) {
    throw std::invalid_argument("[NodeWindowREF] max_res must be non-empty");
  }
  if (critical_res_ < 0 || critical_res_ >= n_res_) {
    throw std::invalid_argument(
        "[NodeWindowREF] critical_res out of range: " +
        std::to_string(critical_res_));
  }
  if (source_id_ < 0 || source_id_ >= n_vertices_ || sink_id_ < 0 ||
      sink_id_ >= n_vertices_) {
    throw std::invalid_argument(
        "[NodeWindowREF] source_id/sink_id out of range");
  }
  // Rejection sentinel: strictly greater than max_res[r] even for huge values
  sentinel_.resize(n_res_);
  for (int r = 0; r < n_res_; ++r) {
    sentinel_[r] = std::max(
        max_res_[r] + 1.0,
        std::nextafter(max_res_[r], std::numeric_limits<double>::infinity()));
  }
  policy_.assign(n_res_, POLICY_ADDITIVE);
  lb_.assign(n_res_, std::vector<double>(n_vertices_, 0.0));
  ub_.resize(n_res_);
  for (int r = 0; r < n_res_; ++r) {
    ub_[r].assign(n_vertices_, max_res_[r]);
  }
  cons_.assign(n_res_, std::vector<double>(n_vertices_, 0.0));
}

void NodeWindowREF::setResourcePolicy(
    const int&                 r,
    const int&                 policy,
    const std::vector<double>& lower,
    const std::vector<double>& upper,
    const std::vector<double>& node_consumption) {
  if (r < 0 || r >= n_res_) {
    throw std::invalid_argument(
        "[NodeWindowREF] resource index out of range: " + std::to_string(r));
  }
  if (policy != POLICY_ADDITIVE && policy != POLICY_WINDOW_WAIT &&
      policy != POLICY_WINDOW_HARD) {
    throw std::invalid_argument(
        "[NodeWindowREF] invalid policy: " + std::to_string(policy));
  }
  // Window policies need a finite horizon: the rejection sentinel must be
  // strictly greater than max_res[r] (with max_res[r] = inf the sentinel
  // collapses to inf and the engine check `res <= max_res[r]` can no longer
  // reject window-infeasible labels), and REF_bwd computes H - ub which
  // would be NaN for an infinite horizon.
  if (policy != POLICY_ADDITIVE && !std::isfinite(max_res_[r])) {
    throw std::invalid_argument(
        "[NodeWindowREF] window policies require finite max_res for "
        "resource " +
        std::to_string(r));
  }
  const std::size_t n = static_cast<std::size_t>(n_vertices_);
  if (lower.size() != n || upper.size() != n || node_consumption.size() != n) {
    throw std::invalid_argument(
        "[NodeWindowREF] lower/upper/node_consumption must have size "
        "number_vertices");
  }
  for (int v = 0; v < n_vertices_; ++v) {
    if (lower[v] > upper[v]) {
      throw std::invalid_argument(
          "[NodeWindowREF] lb > ub for resource " + std::to_string(r) +
          " at node " + std::to_string(v));
    }
  }
  if (r == critical_res_) {
    if (policy != POLICY_ADDITIVE) {
      throw std::invalid_argument(
          "[NodeWindowREF] critical resource must keep POLICY_ADDITIVE");
    }
    for (int v = 0; v < n_vertices_; ++v) {
      if (node_consumption[v] != 0.0) {
        throw std::invalid_argument(
            "[NodeWindowREF] critical resource must have zero "
            "node_consumption");
      }
    }
  }
  policy_[r] = policy;
  lb_[r]     = lower;
  ub_[r]     = upper;
  cons_[r]   = node_consumption;
}

void NodeWindowREF::checkExtensionArgs(
    const std::vector<double>& resource_vector,
    const int&                 tail,
    const int&                 head,
    const std::vector<double>& edge_resource_consumption) const {
  if (tail < 0 || tail >= n_vertices_ || head < 0 || head >= n_vertices_) {
    throw std::invalid_argument(
        "[NodeWindowREF] tail/head out of range [0, number_vertices): tail=" +
        std::to_string(tail) + " head=" + std::to_string(head));
  }
  if (resource_vector.size() < static_cast<std::size_t>(n_res_) ||
      edge_resource_consumption.size() < static_cast<std::size_t>(n_res_)) {
    throw std::invalid_argument(
        "[NodeWindowREF] resource vectors must have size >= n_res (" +
        std::to_string(n_res_) + ")");
  }
}

std::vector<double> NodeWindowREF::REF_fwd(
    const std::vector<double>& cumulative_resource,
    const int&                 tail,
    const int&                 head,
    const std::vector<double>& edge_resource_consumption,
    const std::vector<int>&    partial_path,
    const double&              accummulated_cost) const {
  checkExtensionArgs(cumulative_resource, tail, head, edge_resource_consumption);
  std::vector<double> new_res(n_res_);
  for (int r = 0; r < n_res_; ++r) {
    if (r == critical_res_) {
      // Critical resource is always plain additive (cons == 0 enforced)
      new_res[r] =
          cumulative_resource[r] + edge_resource_consumption[r];
      continue;
    }
    switch (policy_[r]) {
      case POLICY_ADDITIVE: {
        // Node consumption of the head is added on arrival
        // (visit flags are cons = -1)
        new_res[r] = cumulative_resource[r] + edge_resource_consumption[r] +
                     cons_[r][head];
        break;
      }
      case POLICY_WINDOW_WAIT: {
        double T = cumulative_resource[r];
        // Initial label resource is 0; clamp to Source lower bound
        if (tail == source_id_) {
          T = std::max(T, lb_[r][source_id_]);
        }
        const double start = std::max(
            lb_[r][head], T + cons_[r][tail] + edge_resource_consumption[r]);
        new_res[r] = (start <= ub_[r][head] + eps_) ? start : sentinel_[r];
        break;
      }
      case POLICY_WINDOW_HARD:
      default: {
        double T = cumulative_resource[r];
        if (tail == source_id_) {
          T = std::max(T, lb_[r][source_id_]);
        }
        const double value = T + cons_[r][tail] + edge_resource_consumption[r];
        new_res[r] =
            (lb_[r][head] - eps_ <= value && value <= ub_[r][head] + eps_)
                ? value
                : sentinel_[r];
        break;
      }
    }
  }
  return new_res;
}

std::vector<double> NodeWindowREF::REF_bwd(
    const std::vector<double>& cumulative_resource,
    const int&                 tail,
    const int&                 head,
    const std::vector<double>& edge_resource_consumption,
    const std::vector<int>&    partial_path,
    const double&              accummulated_cost) const {
  checkExtensionArgs(cumulative_resource, tail, head, edge_resource_consumption);
  // Backward label lives at `head` and is extended to `tail` (tail/head refer
  // to the original edge orientation).
  std::vector<double> new_res(n_res_);
  for (int r = 0; r < n_res_; ++r) {
    if (r == critical_res_) {
      // Exact reproduction of additiveBackwardREF (ref_callback.cc)
      if (edge_resource_consumption[r] > 0) {
        new_res[r] = cumulative_resource[r] - edge_resource_consumption[r];
      } else {
        new_res[r] = cumulative_resource[r] - 1;
      }
      continue;
    }
    switch (policy_[r]) {
      case POLICY_ADDITIVE: {
        // Node consumption of the arrival node (= tail) is added
        new_res[r] = cumulative_resource[r] + edge_resource_consumption[r] +
                     cons_[r][tail];
        break;
      }
      case POLICY_WINDOW_WAIT:
      case POLICY_WINDOW_HARD:
      default: {
        // Reversed time axis g = H_r - L (L = latest service start time).
        // Sink initial label has g = 0; clamp with the invariant g >= H - ub
        // (idempotent for non-initial labels).
        // NOTE for WINDOW_HARD: this only tracks the upper bounds (latest
        // feasible value); interior lower bounds are not checked (see header).
        const double H   = max_res_[r];
        const double g_h = std::max(cumulative_resource[r], H - ub_[r][head]);
        const double g_t = std::max(
            g_h + cons_[r][tail] + edge_resource_consumption[r],
            H - ub_[r][tail]);
        new_res[r] =
            (g_t <= H - lb_[r][tail] + eps_) ? g_t : sentinel_[r];
        break;
      }
    }
  }
  return new_res;
}

std::vector<double> NodeWindowREF::REF_join(
    const std::vector<double>& fwd_resource,
    const std::vector<double>& bwd_resource,
    const int&                 tail,
    const int&                 head,
    const std::vector<double>& edge_resource_consumption) const {
  checkExtensionArgs(fwd_resource, tail, head, edge_resource_consumption);
  checkExtensionArgs(bwd_resource, tail, head, edge_resource_consumption);
  // tail = node of the forward label, head = node of the backward label
  std::vector<double> new_res(n_res_);
  for (int r = 0; r < n_res_; ++r) {
    if (r == critical_res_) {
      // Fix-up avoidance: replicate the comparison expression of
      // labelling.cc mergeLabels (same operations, same left-to-right
      // association) so the equality check there holds bitwise and the
      // fix-up branch is not taken.
      const double m =
          (edge_resource_consumption[r] == 0) ? 1
                                              : edge_resource_consumption[r];
      new_res[r] = fwd_resource[r] + m + (max_res_[r] - bwd_resource[r]);
      continue;
    }
    switch (policy_[r]) {
      case POLICY_ADDITIVE: {
        // fwd covers (Source, tail], bwd covers [head, Sink) node
        // consumptions; only c[Sink] is missing from the sum.
        new_res[r] = fwd_resource[r] + edge_resource_consumption[r] +
                     bwd_resource[r] + cons_[r][sink_id_];
        break;
      }
      case POLICY_WINDOW_WAIT:
      case POLICY_WINDOW_HARD:
      default: {
        const double H = max_res_[r];
        double       T_f = fwd_resource[r];
        // Source->head single-edge joins: clamp initial label to lb[Source]
        if (tail == source_id_) {
          T_f = std::max(T_f, lb_[r][source_id_]);
        }
        const double g_h = std::max(bwd_resource[r], H - ub_[r][head]);
        const double start_h = std::max(
            lb_[r][head],
            T_f + cons_[r][tail] + edge_resource_consumption[r]);
        // start_h + g_h <= H iff the joined path is window-feasible; the
        // engine checks the returned value against max_res[r] == H.
        new_res[r] = (start_h <= ub_[r][head] + eps_) ? (start_h + g_h)
                                                      : sentinel_[r];
        break;
      }
    }
  }
  return new_res;
}

} // namespace bidirectional
