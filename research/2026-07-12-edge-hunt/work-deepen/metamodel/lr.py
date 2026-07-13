"""Pure-python (stdlib) L2 logistic regression.

Primary optimizer: gradient descent with Barzilai-Borwein steps and a
best-iterate safeguard (deterministic, seedless, init w=0 b=0).
Cross-check optimizer: IRLS/Newton with step-halving. Both minimize
    J = (1/n) * sum CE_i + lambda/(2n) * ||w||^2   (intercept unpenalized)
on standardized features.
"""
import math


def standardize_fit(X):
    n, d = len(X), len(X[0])
    mu = [sum(row[j] for row in X) / n for j in range(d)]
    sd = []
    for j in range(d):
        v = sum((row[j] - mu[j]) ** 2 for row in X) / n
        s = math.sqrt(v)
        sd.append(s if s > 1e-12 else 1.0)   # zero-variance -> centered zeros
    return mu, sd


def standardize_apply(X, mu, sd):
    return [[(row[j] - mu[j]) / sd[j] for j in range(len(mu))] for row in X]


def _sig(z):
    if z >= 0:
        e = math.exp(-z)
        return 1.0 / (1.0 + e)
    e = math.exp(z)
    return e / (1.0 + e)


def predict(Xs, w, b):
    return [_sig(b + sum(wj * xj for wj, xj in zip(w, row))) for row in Xs]


def _loss_grad(Xs, y, w, b, lam):
    n, d = len(Xs), len(w)
    p = predict(Xs, w, b)
    eps = 1e-12
    ce = -sum(yi * math.log(max(pi, eps)) + (1 - yi) * math.log(max(1 - pi, eps))
              for yi, pi in zip(y, p)) / n
    J = ce + lam / (2 * n) * sum(wj * wj for wj in w)
    r = [pi - yi for pi, yi in zip(p, y)]
    gw = [sum(r[i] * Xs[i][j] for i in range(n)) / n + lam / n * w[j] for j in range(d)]
    gb = sum(r) / n
    return J, gw, gb


def fit_gd(Xs, y, lam, max_iter=2000, tol=1e-9):
    """BB gradient descent; returns (w, b, J, n_iter, converged)."""
    d = len(Xs[0])
    w, b = [0.0] * d, 0.0
    J, gw, gb = _loss_grad(Xs, y, w, b, lam)
    bw, bb, bJ = list(w), b, J
    lr = 1.0
    pw, pb, pgw, pgb = None, None, None, None
    it = 0
    for it in range(1, max_iter + 1):
        nw = [wj - lr * gj for wj, gj in zip(w, gw)]
        nb = b - lr * gb
        nJ, ngw, ngb = _loss_grad(Xs, y, nw, nb, lam)
        if nJ < bJ:
            bw, bb, bJ = list(nw), nb, nJ
        # BB1 step from consecutive iterates
        if pw is not None:
            s = [a - c for a, c in zip(nw, pw)] + [nb - pb]
            g = [a - c for a, c in zip(ngw, pgw)] + [ngb - pgb]
            ss = sum(a * a for a in s)
            sg = sum(a * c for a, c in zip(s, g))
            lr = min(max(ss / sg, 1e-4), 1e4) if sg > 1e-18 else 1.0
        pw, pb, pgw, pgb = list(w), b, list(gw), gb
        w, b, J, gw, gb = nw, nb, nJ, ngw, ngb
        ginf = max(abs(gb), max((abs(gj) for gj in gw), default=0.0))
        if ginf < tol:
            return w, b, J, it, True
    return bw, bb, bJ, it, False


def fit_irls(Xs, y, lam, max_iter=100, tol=1e-10):
    """Newton/IRLS cross-check; returns (w, b, J, n_iter, converged)."""
    n, d = len(Xs), len(Xs[0])
    th = [0.0] * (d + 1)                     # [b, w...]
    X1 = [[1.0] + list(row) for row in Xs]
    prevJ = None
    for it in range(1, max_iter + 1):
        p = [_sig(sum(t * x for t, x in zip(th, row))) for row in X1]
        eps = 1e-12
        ce = -sum(yi * math.log(max(pi, eps)) + (1 - yi) * math.log(max(1 - pi, eps))
                  for yi, pi in zip(y, p)) / n
        J = ce + lam / (2 * n) * sum(th[j] ** 2 for j in range(1, d + 1))
        g = [sum((p[i] - y[i]) * X1[i][j] for i in range(n)) / n for j in range(d + 1)]
        for j in range(1, d + 1):
            g[j] += lam / n * th[j]
        # Hessian
        H = [[0.0] * (d + 1) for _ in range(d + 1)]
        for i in range(n):
            wgt = max(p[i] * (1 - p[i]), 1e-10)
            xi = X1[i]
            for a in range(d + 1):
                va = wgt * xi[a]
                Ha = H[a]
                for c in range(a, d + 1):
                    Ha[c] += va * xi[c]
        for a in range(d + 1):
            for c in range(a, d + 1):
                H[a][c] /= n
                H[c][a] = H[a][c]
        for j in range(1, d + 1):
            H[j][j] += lam / n
        step = _solve(H, g)
        # step-halving
        t = 1.0
        for _ in range(40):
            nt = [th[j] - t * step[j] for j in range(d + 1)]
            p2 = [_sig(sum(tj * x for tj, x in zip(nt, row))) for row in X1]
            ce2 = -sum(yi * math.log(max(pi, 1e-12)) + (1 - yi) * math.log(max(1 - pi, 1e-12))
                       for yi, pi in zip(y, p2)) / n
            J2 = ce2 + lam / (2 * n) * sum(nt[j] ** 2 for j in range(1, d + 1))
            if J2 <= J + 1e-14:
                break
            t /= 2
        th = nt
        if prevJ is not None and abs(prevJ - J2) < tol:
            return th[1:], th[0], J2, it, True
        prevJ = J2
    return th[1:], th[0], prevJ, it, False


def _solve(A, bvec):
    """Gaussian elimination with partial pivoting; A (m x m), b (m)."""
    m = len(A)
    M = [row[:] + [bvec[i]] for i, row in enumerate(A)]
    for c in range(m):
        piv = max(range(c, m), key=lambda r: abs(M[r][c]))
        M[c], M[piv] = M[piv], M[c]
        pv = M[c][c]
        if abs(pv) < 1e-14:
            pv = 1e-14
        M[c] = [v / pv for v in M[c]]
        for r in range(m):
            if r != c and M[r][c]:
                f = M[r][c]
                M[r] = [vr - f * vc for vr, vc in zip(M[r], M[c])]
    return [M[r][m] for r in range(m)]
