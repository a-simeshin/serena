package test_repo;

import lombok.Builder;
import lombok.Data;

@Data
@Builder
public class LombokModel {
    private String name;
    private int age;
}
