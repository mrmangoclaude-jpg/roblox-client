"""Local axis-aligned and oriented box queries for movement simulation.

These functions report geometric intersections only. They do not model Roblox
contacts, moving assemblies, friction, character controllers, or replication.
Ray directions are normalized, so ray hit distances use world units. Sweeps
return a fraction of the supplied displacement.
"""
from __future__ import annotations

import math
from typing import NamedTuple

Vector3 = tuple[float, float, float]


class Hit(NamedTuple):
    """An intersection parameter and the outward normal of the hit face."""

    distance: float
    normal: Vector3


def _vector(value: object, name: str) -> Vector3:
    if not isinstance(value, (tuple, list)) or len(value) != 3:
        raise ValueError(f"{name} must have three finite components")
    if any(isinstance(component, bool) or not isinstance(component, (int, float))
           or not math.isfinite(component) for component in value):
        raise ValueError(f"{name} must have three finite components")
    return (float(value[0]), float(value[1]), float(value[2]))


def _bounds(min_bound: object, max_bound: object) -> tuple[Vector3, Vector3]:
    lower, upper = _vector(min_bound, "min_bound"), _vector(max_bound, "max_bound")
    if any(lower[i] >= upper[i] for i in range(3)):
        raise ValueError("AABB bounds must have positive extent on every axis")
    return lower, upper


def _slab(origin: Vector3, direction: Vector3, lower: Vector3, upper: Vector3,
          max_parameter: float) -> Hit | None:
    # An origin strictly inside the box is already penetrating. A zero normal
    # makes that state explicit and avoids inventing a unique exit face.
    if all(lower[i] < origin[i] < upper[i] for i in range(3)):
        return Hit(0.0, (0.0, 0.0, 0.0))

    near = -math.inf
    far = math.inf
    near_normal = (0.0, 0.0, 0.0)
    for axis in range(3):
        component = direction[axis]
        if component == 0.0:
            if origin[axis] < lower[axis] or origin[axis] > upper[axis]:
                return None
            continue
        first = (lower[axis] - origin[axis]) / component
        second = (upper[axis] - origin[axis]) / component
        if first <= second:
            entry, exit = first, second
            normal = tuple(-1.0 if i == axis else 0.0 for i in range(3))
        else:
            entry, exit = second, first
            normal = tuple(1.0 if i == axis else 0.0 for i in range(3))
        if entry > near:
            near, near_normal = entry, normal
        far = min(far, exit)
        if near > far:
            return None

    if far < 0.0 or near < 0.0 or near > max_parameter:
        return None
    return Hit(near, near_normal)


def ray_aabb(origin: object, direction: object, min_bound: object,
             max_bound: object, max_distance: float) -> Hit | None:
    """Cast a finite ray against an axis-aligned box.

    ``direction`` is normalized internally, and ``max_distance`` is measured
    in world units. Starting strictly inside returns distance zero and a zero
    normal. A surface hit returns its outward axis normal. Zero direction,
    invalid bounds, and non-finite/negative distances are rejected.
    """
    start = _vector(origin, "origin")
    vector = _vector(direction, "direction")
    lower, upper = _bounds(min_bound, max_bound)
    if isinstance(max_distance, bool) or not isinstance(max_distance, (int, float)) \
            or not math.isfinite(max_distance) or max_distance < 0:
        raise ValueError("max_distance must be finite and non-negative")
    magnitude = math.hypot(*vector)
    if magnitude == 0.0:
        raise ValueError("direction must be non-zero")
    unit = tuple(component / magnitude for component in vector)
    return _slab(start, unit, lower, upper, float(max_distance))


def rotation_matrix(value: object) -> tuple[float, ...]:
    """Validate a row-major local-to-world rigid rotation, without repairing it."""
    if not isinstance(value, (tuple, list)) or len(value) != 9:
        raise ValueError('rotation must contain nine finite numbers')
    a, b, c, d, e, f, g, h, i = value
    isfinite = math.isfinite
    if (type(a) is float and type(b) is float and type(c) is float
            and type(d) is float and type(e) is float and type(f) is float
            and type(g) is float and type(h) is float and type(i) is float):
        if not (isfinite(a) and isfinite(b) and isfinite(c)
                and isfinite(d) and isfinite(e) and isfinite(f)
                and isfinite(g) and isfinite(h) and isfinite(i)):
            raise ValueError('rotation must contain nine finite numbers')
    else:
        for v in value:
            if isinstance(v, bool) or not isinstance(v, (int, float)) or not isfinite(v):
                raise ValueError('rotation must contain nine finite numbers')
        a, b, c, d, e, f, g, h, i = (float(a), float(b), float(c),
                                     float(d), float(e), float(f),
                                     float(g), float(h), float(i))
    if (abs(a*a + d*d + g*g - 1.0) > 1e-5
            or abs(a*b + d*e + g*h) > 1e-5
            or abs(a*c + d*f + g*i) > 1e-5
            or abs(b*b + e*e + h*h - 1.0) > 1e-5
            or abs(b*c + e*f + h*i) > 1e-5
            or abs(c*c + f*f + i*i - 1.0) > 1e-5):
        raise ValueError('rotation must be orthonormal')
    if abs(a*(e*i - f*h) - b*(d*i - f*g) + c*(d*h - e*g) - 1.0) > 1e-5:
        raise ValueError('rotation must be right-handed')
    return (a, b, c, d, e, f, g, h, i)


def ray_obb(origin: object, direction: object, center: object, half_size: object,
            rotation: object, max_distance: float) -> Hit | None:
    """Cast in box-local space and return a world distance and face normal.

    The input rotation is a rigid local-to-world matrix. Its transpose is the
    inverse; scale, shear, reflections and missing rotation data are rejected.
    """
    start,vector = _vector(origin,'origin'),_vector(direction,'direction')
    middle,half = _vector(center,'center'),_vector(half_size,'half_size')
    if any(v <= 0 for v in half):
        raise ValueError('half_size must be positive')
    matrix = rotation_matrix(rotation)
    offset = tuple(start[i]-middle[i] for i in range(3))
    local = [sum(matrix[3*j+i]*offset[j] for j in range(3)) for i in range(3)]
    vector = tuple(sum(matrix[3*j+i]*vector[j] for j in range(3)) for i in range(3))
    # Floating-point inverse transforms can place an exact surface point a few
    # ulps inside its own box. Snap only that numerical boundary ambiguity.
    for i in range(3):
        tolerance = 1e-10*max(1.0,half[i])
        if abs(local[i]-half[i]) <= tolerance:local[i] = half[i]
        elif abs(local[i]+half[i]) <= tolerance:local[i] = -half[i]
    hit = ray_aabb(local,vector,tuple(-v for v in half),half,max_distance)
    if hit is None:return None
    normal = tuple(sum(matrix[3*i+j]*hit.normal[j] for j in range(3)) for i in range(3))
    magnitude = math.hypot(*normal)
    if magnitude:normal = tuple(v/magnitude for v in normal)
    return Hit(hit.distance,normal)


def sweep_aabb_horizontal(center: object, half_size: object, displacement: object,
                          min_bound: object, max_bound: object) -> Hit | None:
    """Sweep a horizontal (X/Z) AABB against a stationary AABB.

    The actor's vertical position and height are ignored. The obstacle is
    expanded by the actor's X/Z half-size (Minkowski sum), then the center is
    swept through that box. A returned distance is the [0, 1] fraction of the
    requested displacement. Initial horizontal overlap returns ``(0, 0 normal)``.
    """
    point = _vector(center, "center")
    half = _vector(half_size, "half_size")
    delta = _vector(displacement, "displacement")
    lower, upper = _bounds(min_bound, max_bound)
    if any(component < 0.0 for component in half):
        raise ValueError("half_size components must be non-negative")
    if half[0] == 0.0 or half[2] == 0.0:
        raise ValueError("horizontal half_size must be positive")

    # This helper is deliberately 2D in X/Z. Give the slab query an open,
    # nonzero Y interval containing the center so vertical motion is ignored.
    expanded_min = (lower[0] - half[0], point[1] - 1.0, lower[2] - half[2])
    expanded_max = (upper[0] + half[0], point[1] + 1.0, upper[2] + half[2])
    if delta[0] == 0.0 and delta[2] == 0.0:
        if expanded_min[0] < point[0] < expanded_max[0] \
                and expanded_min[2] < point[2] < expanded_max[2]:
            return Hit(0.0, (0.0, 0.0, 0.0))
        return None

    horizontal_delta = (delta[0], 0.0, delta[2])
    return _slab(point, horizontal_delta, expanded_min, expanded_max, 1.0)


def sweep_aabb_obb(center: object, half_size: object, displacement: object,
                   obstacle_center: object, obstacle_half_size: object,
                   obstacle_rotation: object) -> Hit | None:
    """Continuous translation of an AABB against a fixed oriented box.

    Intersect the time intervals on all 15 separating axes. The returned
    distance is a fraction of displacement, and the normal points out of the
    obstacle. Strict initial penetration has no unique normal and is explicit.
    Rotating bodies during a sweep and penetration recovery are not modeled.
    See Eberly, Dynamic Collision Detection using Oriented Bounding Boxes.
    """
    point = _vector(center, 'center')
    half = _vector(half_size, 'half_size')
    delta = _vector(displacement, 'displacement')
    middle = _vector(obstacle_center, 'obstacle_center')
    extent = _vector(obstacle_half_size, 'obstacle_half_size')
    if any(v <= 0 for v in half + extent):
        raise ValueError('box half sizes must be positive')
    matrix = rotation_matrix(obstacle_rotation)
    basis = ((1., 0., 0.), (0., 1., 0.), (0., 0., 1.))
    other = tuple(tuple(matrix[3*i+j] for i in range(3)) for j in range(3))
    axes = list(basis + other)
    for a in basis:
        for b in other:
            cross = (a[1]*b[2]-a[2]*b[1], a[2]*b[0]-a[0]*b[2], a[0]*b[1]-a[1]*b[0])
            length = math.hypot(*cross)
            if length > 1e-12:
                axes.append(tuple(v/length for v in cross))
    offset = tuple(point[i]-middle[i] for i in range(3))
    near, far, normal = -math.inf, math.inf, (0., 0., 0.)
    penetrating = True
    for axis in axes:
        position = sum(offset[i]*axis[i] for i in range(3))
        speed = sum(delta[i]*axis[i] for i in range(3))
        radius = sum(half[i]*abs(axis[i]) for i in range(3))
        radius += sum(extent[j]*abs(sum(other[j][i]*axis[i] for i in range(3))) for j in range(3))
        if not all(math.isfinite(v) for v in (position, speed, radius)):
            raise ValueError('sweep projection exceeds finite range')
        tolerance = 1e-10*max(1., radius)
        if abs(position) >= radius-tolerance:
            penetrating = False
        if abs(abs(position)-radius) <= tolerance:
            position = math.copysign(radius, position)
        if speed == 0.:
            if abs(position) > radius:
                return None
            continue
        entry, exit = (-radius-position)/speed, (radius-position)/speed
        sign = -1. if speed > 0 else 1.
        if entry > exit:
            entry, exit = exit, entry
        if entry > near:
            near, normal = entry, tuple(sign*v for v in axis)
        far = min(far, exit)
        if near > far:
            return None
    if penetrating:
        return Hit(0., (0., 0., 0.))
    if far < 0. or near < 0. or near > 1.:
        return None
    return Hit(near, normal)


def shallow_overlap_allows_motion(center, half_size, displacement,
                                  obstacle_center, obstacle_half_size,
                                  obstacle_rotation, *, max_depth=0.15):
    """Allow requested escape/tangent motion from a small box penetration.

    All nearest separating planes must retain or reduce their penetration.
    This never creates a displacement or chooses a depenetration direction.
    Deep overlaps, centered/ambiguous overlaps and motion into a nearest plane
    remain blocked. Callers must still sweep against every other obstacle.
    """
    point, half = _vector(center, 'center'), _vector(half_size, 'half_size')
    delta = _vector(displacement, 'displacement')
    middle = _vector(obstacle_center, 'obstacle_center')
    extent = _vector(obstacle_half_size, 'obstacle_half_size')
    matrix = rotation_matrix(obstacle_rotation)
    if any(v <= 0 for v in half + extent):
        raise ValueError('box half sizes must be positive')
    if (type(max_depth) not in (int, float) or not math.isfinite(max_depth)
            or max_depth < 0):
        raise ValueError('max_depth must be finite and non-negative')
    if math.hypot(*delta) == 0:
        return False
    basis = ((1., 0., 0.), (0., 1., 0.), (0., 0., 1.))
    other = tuple(tuple(matrix[3*i+j] for i in range(3)) for j in range(3))
    axes = list(basis + other)
    for a in basis:
        for b in other:
            cross = (a[1]*b[2]-a[2]*b[1], a[2]*b[0]-a[0]*b[2], a[0]*b[1]-a[1]*b[0])
            length = math.hypot(*cross)
            if length > 1e-12:
                axes.append(tuple(v/length for v in cross))
    offset = tuple(point[i]-middle[i] for i in range(3))
    planes = []
    for axis in axes:
        position = sum(offset[i]*axis[i] for i in range(3))
        radius = sum(half[i]*abs(axis[i]) for i in range(3))
        radius += sum(extent[j]*abs(sum(other[j][i]*axis[i] for i in range(3))) for j in range(3))
        depth = radius-abs(position)
        if not math.isfinite(depth) or depth <= 1e-10*max(1., radius):
            return False
        speed = sum(delta[i]*axis[i] for i in range(3))
        planes.append((depth, position, speed))
    nearest = min(row[0] for row in planes)
    if nearest > max_depth:
        return False
    return all(abs(position) > 1e-10 and speed*math.copysign(1., position) >= -1e-10
               for depth, position, speed in planes if depth <= nearest+1e-9)
