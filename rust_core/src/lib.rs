use pyo3::prelude::*;
use pyo3::exceptions::PyRuntimeError;
use rand::Rng;
use std::time::Instant;

#[pyfunction]
fn get_morton_code_4d(x: f64, y: f64, z: f64, t: f64) -> u64 {
    let xi = (x.clamp(0.0, 1.0) * 65535.0) as u64;
    let yi = (y.clamp(0.0, 1.0) * 65535.0) as u64;
    let zi = (z.clamp(0.0, 1.0) * 65535.0) as u64;
    let ti = (t.clamp(0.0, 1.0) * 65535.0) as u64;
    
    let mut code = 0u64;
    for i in 0..16 {
        let bit_x = (xi >> i) & 1;
        let bit_y = (yi >> i) & 1;
        let bit_z = (zi >> i) & 1;
        let bit_t = (ti >> i) & 1;
        
        code |= bit_x << (4 * i);
        code |= bit_y << (4 * i + 1);
        code |= bit_z << (4 * i + 2);
        code |= bit_t << (4 * i + 3);
    }
    code
}

#[pyfunction]
fn fast_binary_search_knn(memory: Vec<Vec<f64>>, count: usize, target_code: u64, k: usize) -> Vec<f64> {
    if count == 0 || memory.is_empty() {
        return vec![0.0; k];
    }
    
    let mut left = 0isize;
    let mut right = (count - 1) as isize;
    let mut mid = 0isize;
    
    while left <= right {
        mid = left + (right - left) / 2;
        let val_mid = memory[mid as usize][0] as u64;
        if val_mid == target_code {
            break;
        } else if val_mid < target_code {
            left = mid + 1;
        } else {
            right = mid - 1;
        }
    }
    
    let mut results = vec![0.0; k];
    let mut r_idx = 0;
    let mut l_ptr = mid;
    let mut r_ptr = mid + 1;
    
    while r_idx < k {
        if l_ptr >= 0 && (r_ptr as usize) < count {
            let val_l = memory[l_ptr as usize][0] as u64;
            let val_r = memory[r_ptr as usize][0] as u64;
            let dist_l = if target_code > val_l { target_code - val_l } else { val_l - target_code };
            let dist_r = if target_code > val_r { target_code - val_r } else { val_r - target_code };
            
            if dist_l <= dist_r {
                results[r_idx] = memory[l_ptr as usize][1];
                l_ptr -= 1;
            } else {
                results[r_idx] = memory[r_ptr as usize][1];
                r_ptr += 1;
            }
        } else if l_ptr >= 0 {
            results[r_idx] = memory[l_ptr as usize][1];
            l_ptr -= 1;
        } else if (r_ptr as usize) < count {
            results[r_idx] = memory[r_ptr as usize][1];
            r_ptr += 1;
        } else {
            break;
        }
        r_idx += 1;
    }
    results
}

#[pyfunction]
#[pyo3(signature = (matriz, pasos=25, simulaciones=1000))]
fn simular_factor_k_vectorizado(
    matriz: Vec<Vec<f64>>,
    pasos: usize,
    simulaciones: usize,
) -> PyResult<f64> {
    let mut rng = rand::thread_rng();
    
    if matriz.len() < 3 || matriz[0].len() < 3 {
        return Ok(0.0);
    }
    
    let mut thresholds = vec![[0.0; 3]; 3];
    for i in 0..3 {
        thresholds[i][0] = matriz[i][0];
        thresholds[i][1] = matriz[i][0] + matriz[i][1];
        thresholds[i][2] = matriz[i][0] + matriz[i][1] + matriz[i][2];
    }
    
    let mut fisiones_totales = vec![0; simulaciones];
    let mut pasos_vivos = vec![1; simulaciones];
    let mut estados = vec![1; simulaciones];
    
    for _ in 0..pasos {
        for s in 0..simulaciones {
            let e = estados[s] as usize;
            let r: f64 = rng.gen();
            
            let siguiente_estado = if r < thresholds[e][0] {
                0
            } else if r < thresholds[e][1] {
                1
            } else {
                2
            };
            
            if siguiente_estado > 0 {
                pasos_vivos[s] += 1;
            }
            if siguiente_estado == 2 {
                fisiones_totales[s] += 1;
            }
            estados[s] = siguiente_estado;
        }
    }
    
    let mut sum_k = 0.0;
    for s in 0..simulaciones {
        let v = pasos_vivos[s];
        let divisor = if v > 0 { v as f64 } else { 1.0 };
        sum_k += fisiones_totales[s] as f64 / divisor;
    }
    
    Ok(sum_k / simulaciones as f64)
}

#[pyclass]
struct LucyTimeAuditor {
    #[pyo3(get, set)]
    umbral_nanosegundos: u128,
}

#[pymethods]
impl LucyTimeAuditor {
    #[new]
    fn new(limite_ns: u128) -> Self {
        LucyTimeAuditor { umbral_nanosegundos: limite_ns }
    }

    fn auditar_potencial_tensor(&self, f_vector: &Bound<'_, PyAny>) -> PyResult<u128> {
        let tiempo_inicial = Instant::now();

        f_vector.call0()?;

        let duracion = tiempo_inicial.elapsed().as_nanos();

        if duracion > self.umbral_nanosegundos {
            return Err(PyRuntimeError::new_err(
                "Singularidad Temporal Detectada: Tráfico bloqueado por Q-Balam."
            ));
        }

        Ok(duracion)
    }
}

#[pymodule]
fn tzanix_rust_core(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(get_morton_code_4d, m)?)?;
    m.add_function(wrap_pyfunction!(fast_binary_search_knn, m)?)?;
    m.add_function(wrap_pyfunction!(simular_factor_k_vectorizado, m)?)?;
    m.add_class::<LucyTimeAuditor>()?;
    Ok(())
}
